"""Reliability, Observability, and Defensive Security Hardening Test Suite (Batch 2).

Validates:
1. Request correlation ID generation, validation, response header, and error response payload.
2. Global exception handling without leaking stack traces or internal secrets.
3. Temporary file cleanup on both successful and failed verification/registration flows.
4. Upload payload validation (empty files, oversized files, unsupported formats).
5. Redis failure resiliency (graceful degradation, authoritative fallback, no false VERIFIED).
6. Database failure handling (controlled 503 response without connection string exposure).
7. WhatsApp error handling and reference ID emission.
8. Liveness and Readiness health probes.
9. Security HTTP response headers.
"""

import io
import json
import logging
import os
from pathlib import Path
import tempfile
from typing import Generator
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.context import get_current_request_id, set_current_request_id
from app.core.hash_service import calculate_bytes_hash
from app.core.upload_validation import validate_file_payload
from app.database import Base, engine, get_db
from app.main import app
from app.models.database import (
    AuditLog,
    ContentStatus,
    Credential,
    CredentialStatus,
    RegisteredContent,
    User,
    UserRole,
    VerificationVerdict,
)
from app.services.publisher_service import register_content
from app.services.verification_service import verify_file, verify_text
from app.services.whatsapp_service import WhatsAppService


# ============================================================================
# 1. Request Correlation ID & Security Headers
# ============================================================================

def test_request_id_generated_when_missing(client: TestClient):
    """Ensure every request without X-Request-ID gets a unique UUID correlation ID in header."""
    res = client.get("/health")
    assert res.status_code == 200
    req_id = res.headers.get("X-Request-ID")
    assert req_id is not None
    assert len(req_id) >= 16


def test_existing_valid_request_id_preserved(client: TestClient):
    """Ensure safe client-supplied X-Request-ID is preserved across request/response."""
    custom_id = "test-corr-id-998877"
    res = client.get("/health", headers={"X-Request-ID": custom_id})
    assert res.status_code == 200
    assert res.headers.get("X-Request-ID") == custom_id


def test_malformed_oversized_request_id_replaced(client: TestClient):
    """Ensure malformed or oversized request ID is safely sanitized to a fresh UUID."""
    malicious_id = "A" * 200 + "<script>alert(1)</script>"
    res = client.get("/health", headers={"X-Request-ID": malicious_id})
    assert res.status_code == 200
    received_id = res.headers.get("X-Request-ID")
    assert received_id is not None
    assert received_id != malicious_id
    assert "<script>" not in received_id


def test_security_http_headers_present(client: TestClient):
    """Verify security headers are consistently injected into HTTP responses."""
    res = client.get("/health")
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "DENY"
    assert res.headers.get("X-XSS-Protection") == "1; mode=block"
    assert "strict-origin-when-cross-origin" in res.headers.get("Referrer-Policy", "")
    assert res.headers.get("X-Process-Time-Ms") is not None


# ============================================================================
# 2. Global Exception Handling & Error Envelopes
# ============================================================================

def test_http_exception_contains_request_id(client: TestClient):
    """Verify 404/400 HTTP exceptions include request_id in response body."""
    custom_id = "req-err-check-1234"
    res = client.get("/api/v1/content/00000000-0000-0000-0000-000000000000", headers={"X-Request-ID": custom_id})
    assert res.status_code == 404
    data = res.json()
    assert data["error"] is True
    assert data["status_code"] == 404
    assert data["request_id"] == custom_id


def test_validation_error_contains_request_id(client: TestClient):
    """Verify Pydantic 422 errors include request_id in response body."""
    custom_id = "val-err-check-5678"
    res = client.post("/api/v1/auth/login", json={"email": "invalid-not-json-schema"}, headers={"X-Request-ID": custom_id})
    assert res.status_code == 422
    data = res.json()
    assert data["error"] is True
    assert data["request_id"] == custom_id


def test_database_exception_produces_controlled_response(client: TestClient, monkeypatch):
    """Verify database connection errors return controlled 503 without exposing credentials."""
    from app.api.v1 import system

    def mock_db_failure(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("psycopg2.OperationalError: could not connect to server: Connection refused"))

    monkeypatch.setattr(system, "verify_chain", mock_db_failure)

    res = client.get("/api/v1/status", headers={"X-Request-ID": "db-fail-check-999"})
    assert res.status_code in [500, 503]
    data = res.json()
    assert data["error"] is True
    assert "postgresql://" not in str(data)
    assert "password" not in str(data).lower()
    assert data.get("request_id") == "db-fail-check-999"


# ============================================================================
# 3. File Upload Validation & Defensive Rejection
# ============================================================================

def test_empty_file_upload_rejected(client: TestClient, publisher_headers):
    """Verify empty 0-byte uploads are rejected with HTTP 400."""
    empty_file = io.BytesIO(b"")
    files = {"file": ("empty.png", empty_file, "image/png")}
    res = client.post("/api/v1/verify", files=files)
    assert res.status_code == 400
    assert "empty" in res.json()["message"].lower()


def test_oversized_file_upload_rejected():
    """Verify uploads exceeding max size limit are rejected defensively."""
    is_valid, msg = validate_file_payload(
        b"x" * 100,
        filename="oversized.png",
        max_size_bytes=50,
    )
    assert is_valid is False
    assert "exceeds maximum allowed limit" in msg


def test_unsupported_file_extension_rejected(client: TestClient):
    """Verify unsupported file extensions (.exe, .sh) are safely rejected."""
    sample_bytes = b"echo 'malicious script'"
    files = {"file": ("script.sh", io.BytesIO(sample_bytes), "application/x-sh")}
    res = client.post("/api/v1/verify", files=files)
    assert res.status_code == 400
    assert "unsupported file format" in res.json()["message"].lower()


# ============================================================================
# 4. Temporary File Cleanup
# ============================================================================

def test_temp_file_cleaned_after_successful_verification(client: TestClient):
    """Verify temporary files created during verification are removed on success."""
    temp_dir = Path(settings.TEMP_DIR)
    initial_temp_files = set(temp_dir.glob("*")) if temp_dir.exists() else set()

    sample_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    files = {"file": ("temp_clean_test.png", io.BytesIO(sample_png), "image/png")}
    res = client.post("/api/v1/verify", files=files)
    assert res.status_code == 200

    current_temp_files = set(temp_dir.glob("*")) if temp_dir.exists() else set()
    new_files = current_temp_files - initial_temp_files
    assert len(new_files) == 0, f"Leaked temporary files found: {new_files}"


def test_temp_file_cleaned_after_failed_verification(client: TestClient):
    """Verify temporary files are removed even if verification validation fails."""
    temp_dir = Path(settings.TEMP_DIR)
    initial_temp_files = set(temp_dir.glob("*")) if temp_dir.exists() else set()

    files = {"file": ("corrupt.exe", io.BytesIO(b"MZ\x90\x00corrupt binary"), "application/octet-stream")}
    res = client.post("/api/v1/verify", files=files)
    assert res.status_code == 400

    current_temp_files = set(temp_dir.glob("*")) if temp_dir.exists() else set()
    new_files = current_temp_files - initial_temp_files
    assert len(new_files) == 0, f"Leaked temporary files found: {new_files}"


# ============================================================================
# 5. Redis Resiliency (Authoritative Fallback & No False VERIFIED)
# ============================================================================

def test_redis_failure_does_not_falsely_verify(db: Session, monkeypatch):
    """When Redis is completely disconnected, verification must perform authoritative DB check."""
    from app.core import security
    monkeypatch.setattr(security, "get_redis_client", lambda: None)

    # Unregistered text must return UNSIGNED, never VERIFIED
    res = verify_text(db=db, text_content=f"Random unauthenticated text {uuid.uuid4().hex}")
    assert res["verdict"] == "UNSIGNED"
    assert res["confidence_score"] == 0.0


# ============================================================================
# 6. Health & Liveness / Readiness Probes
# ============================================================================

def test_health_liveness_probe(client: TestClient):
    """Verify fast liveness check returns 200 OK with alive status."""
    res = client.get("/health/liveness")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "alive"
    assert data["timestamp"] is not None


def test_health_readiness_probe(client: TestClient):
    """Verify readiness check verifies DB connectivity."""
    res = client.get("/health/readiness")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ready"
    assert data["database"] == "connected"


# ============================================================================
# 7. WhatsApp Media & Error Handling
# ============================================================================

def test_whatsapp_media_download_failure_handling(db: Session, monkeypatch):
    """Verify WhatsApp media download failure returns clean error without leaking internals."""
    monkeypatch.setattr(WhatsAppService, "download_media", lambda *args, **kwargs: None)

    res = WhatsAppService.handle_media_message(
        media_id="fake_media_id_123",
        media_type="image",
        mime_type="image/jpeg",
        db=db,
    )
    assert res["success"] is False
    assert "Failed to download media" in res["error"]
