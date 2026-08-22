"""Unit and integration tests for WhatsApp Service, Webhook Endpoints, Rate Limiting, Retries, and Caching."""

import io
import json
import time
from unittest.mock import MagicMock, patch
import uuid
import httpx
import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models.database import (
    ContentType,
    Credential,
    CredentialStatus,
    CredentialType,
    RegisteredContent,
    User,
    UserRole,
    VerificationVerdict,
)
from app.services.auth_service import register_publisher
from app.services.publisher_service import register_content
from app.services.whatsapp_service import (
    WhatsAppService,
    cleanup_temp_files,
    execute_with_retry,
    format_invalid_response,
    format_rate_limit_response,
    format_suspicious_response,
    format_unsigned_response,
    format_verified_response,
    handle_webhook,
    process_message,
    validate_media_file,
    verify_webhook,
)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_verify_webhook_success():
    """Test webhook verification with valid token."""
    mode = "subscribe"
    token = settings.WHATSAPP_VERIFY_TOKEN
    challenge = "1234567890"

    result = verify_webhook(mode=mode, token=token, challenge=challenge)
    assert result == challenge


def test_verify_webhook_invalid_token():
    """Test webhook verification failure with invalid token."""
    with pytest.raises(ValueError):
        verify_webhook(mode="subscribe", token="wrong-token", challenge="12345")


def test_webhook_get_endpoint(client):
    """Test GET /api/v1/webhook/whatsapp with Meta Hub query parameters."""
    response = client.get(
        "/api/v1/webhook/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": settings.WHATSAPP_VERIFY_TOKEN,
            "hub.challenge": "987654321",
        },
    )
    assert response.status_code == 200
    assert response.text == "987654321"


def test_webhook_get_endpoint_forbidden(client):
    """Test GET /api/v1/webhook/whatsapp with mismatched token returns 403."""
    response = client.get(
        "/api/v1/webhook/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "invalid-token",
            "hub.challenge": "987654321",
        },
    )
    assert response.status_code == 403


def test_response_templates():
    """Test WhatsApp Markdown response message formatting."""
    # 1. Verified Response
    verified_evidence = {
        "publisher_organization": "Ministry of Electronics & IT",
        "original_filename": "official_statement.pdf",
        "chain_block_id": 42,
        "signature_valid": True,
        "sha256_match": True,
        "perceptual_hash": {"similarity_percentage": 100},
    }
    ver_text = format_verified_response(verified_evidence, confidence=0.99)
    assert "OFFICIAL GOVERNMENT CONTENT VERIFIED" in ver_text
    assert "Ministry of Electronics & IT" in ver_text
    assert "Block #42" in ver_text
    assert "SHA-256 Hash" in ver_text

    # 2. Suspicious Response
    susp_evidence = {
        "publisher_organization": "Press Information Bureau",
        "perceptual_hash": {"similarity_percentage": 78},
        "notice": "Media altered",
    }
    susp_text = format_suspicious_response(susp_evidence, confidence=0.78)
    assert "SUSPICIOUS / ALTERED CONTENT DETECTED" in susp_text
    assert "78%" in susp_text

    # 3. Unsigned Response
    unsign_text = format_unsigned_response()
    assert "NO OFFICIAL RECORD FOUND (UNSIGNED)" in unsign_text

    # 4. Invalid Response
    inv_text = format_invalid_response("Corrupted file format")
    assert "VERIFICATION FAILED / INVALID" in inv_text
    assert "Corrupted file format" in inv_text

    # 5. Rate Limit Response
    rl_text = format_rate_limit_response()
    assert "Rate Limit Exceeded" in rl_text


def test_process_text_greeting(db: Session):
    """Test text greeting / help triggers help menu."""
    unique_phone = f"91{uuid.uuid4().int % 10000000000:010d}"
    message = {
        "from": unique_phone,
        "id": f"wamid.{uuid.uuid4().hex}",
        "type": "text",
        "text": {"body": "help"},
    }
    with patch("app.services.whatsapp_service.WhatsAppService.send_whatsapp_message") as mock_send:
        mock_send.return_value = True
        res = process_message(message=message, sender_name="John Doe", db=db)
        assert res.get("type") == "help"
        assert mock_send.called
        sent_text = mock_send.call_args[1]["message_text"]
        assert "Welcome John Doe" in sent_text


def test_process_text_verification(db: Session):
    """Test text verification against registered official statement."""
    email = f"whatsapp_pub_{uuid.uuid4().hex[:6]}@gov.in"
    user = register_publisher(
        db=db,
        email=email,
        password="PublisherPassword#123",
        organization_name="Ministry of Information",
        organization_domain="gov.in",
    )
    cred = user.credentials[0]

    official_text = f"Official Press Release: National AI Framework Launched {uuid.uuid4().hex[:6]}."
    upload_file = UploadFile(
        filename="press_release.txt",
        file=io.BytesIO(official_text.encode("utf-8")),
    )
    register_content(
        db=db,
        publisher=user,
        upload_file=upload_file,
    )

    unique_phone = f"91{uuid.uuid4().int % 10000000000:010d}"
    message = {
        "from": unique_phone,
        "id": f"wamid.{uuid.uuid4().hex}",
        "type": "text",
        "text": {"body": official_text},
    }

    with patch("app.services.whatsapp_service.WhatsAppService.send_whatsapp_message") as mock_send:
        mock_send.return_value = True
        res = process_message(message=message, sender_name="Citizen", db=db)
        assert res.get("verdict") == "VERIFIED"
        assert mock_send.called
        sent_text = mock_send.call_args[1]["message_text"]
        assert "OFFICIAL GOVERNMENT CONTENT VERIFIED" in sent_text


def test_per_user_rate_limiting(db: Session):
    """Test that submitting requests beyond rate limit sends rate limit notice."""
    rate_limited_phone = f"91{uuid.uuid4().int % 10000000000:010d}"

    with patch("app.services.whatsapp_service.WhatsAppService.send_whatsapp_message") as mock_send:
        mock_send.return_value = True

        # Send 10 messages (limit)
        for i in range(10):
            msg = {
                "from": rate_limited_phone,
                "id": f"wamid.rate_{i}_{uuid.uuid4().hex}",
                "type": "text",
                "text": {"body": "help"},
            }
            res = process_message(message=msg, sender_name="Citizen", db=db)
            assert res.get("type") == "help"

        # 11th message should be rate limited
        rate_limited_msg = {
            "from": rate_limited_phone,
            "id": f"wamid.rate_11_{uuid.uuid4().hex}",
            "type": "text",
            "text": {"body": "help"},
        }
        res_limit = process_message(message=rate_limited_msg, sender_name="Citizen", db=db)
        assert res_limit.get("type") == "rate_limited"
        assert mock_send.called
        last_sent = mock_send.call_args[1]["message_text"]
        assert "Rate Limit Exceeded" in last_sent


def test_retry_logic_transient_5xx():
    """Test retry logic retries transient 5xx errors and succeeds upon recovery."""
    mock_func = MagicMock()
    # Fails twice with 503, succeeds on 3rd attempt with 200
    res_503 = httpx.Response(503, request=httpx.Request("POST", "http://meta.test"))
    res_200 = httpx.Response(200, request=httpx.Request("POST", "http://meta.test"))
    mock_func.side_effect = [res_503, res_503, res_200]

    with patch("time.sleep") as mock_sleep:
        final_res = execute_with_retry(mock_func, max_retries=3, base_delay=0.1)
        assert final_res is not None
        assert final_res.status_code == 200
        assert mock_func.call_count == 3
        assert mock_sleep.call_count == 2


def test_retry_logic_permanent_4xx_no_retry():
    """Test retry logic does NOT retry permanent 4xx client errors."""
    mock_func = MagicMock()
    res_404 = httpx.Response(404, request=httpx.Request("GET", "http://meta.test"))
    mock_func.return_value = res_404

    with patch("time.sleep") as mock_sleep:
        final_res = execute_with_retry(mock_func, max_retries=3, base_delay=0.1)
        assert final_res is not None
        assert final_res.status_code == 404
        assert mock_func.call_count == 1
        assert mock_sleep.call_count == 0


def test_message_deduplication(db: Session):
    """Test that re-delivered webhook message IDs are skipped."""
    duplicate_msg_id = f"wamid.dup_{uuid.uuid4().hex}"
    phone = f"91{uuid.uuid4().int % 10000000000:010d}"

    message = {
        "from": phone,
        "id": duplicate_msg_id,
        "type": "text",
        "text": {"body": "help"},
    }

    with patch("app.services.whatsapp_service.WhatsAppService.send_whatsapp_message") as mock_send:
        mock_send.return_value = True

        # First delivery -> processes normally
        res1 = process_message(message=message, sender_name="Citizen", db=db)
        assert res1.get("type") == "help"

        # Second delivery with same msg_id -> skipped as duplicate
        res2 = process_message(message=message, sender_name="Citizen", db=db)
        assert res2.get("type") == "duplicate_skipped"


def test_redis_verification_caching(db: Session):
    """Test that identical text queries retrieve cached verification results."""
    unique_text = f"Official communique {uuid.uuid4().hex}"
    phone1 = f"91{uuid.uuid4().int % 10000000000:010d}"
    phone2 = f"91{uuid.uuid4().int % 10000000000:010d}"

    msg1 = {
        "from": phone1,
        "id": f"wamid.c1_{uuid.uuid4().hex}",
        "type": "text",
        "text": {"body": unique_text},
    }

    with patch("app.services.whatsapp_service.WhatsAppService.send_whatsapp_message") as mock_send, \
         patch("app.services.whatsapp_service.verify_text") as mock_verify:
        mock_send.return_value = True
        mock_verify.return_value = {
            "verification_id": str(uuid.uuid4()),
            "verdict": "UNSIGNED",
            "confidence_score": 0.0,
            "evidence_bundle": {},
        }

        # First request runs verification
        res1 = process_message(message=msg1, sender_name="Citizen 1", db=db)
        assert mock_verify.call_count == 1

        # Second request with same content should hit cache
        msg2 = {
            "from": phone2,
            "id": f"wamid.c2_{uuid.uuid4().hex}",
            "type": "text",
            "text": {"body": unique_text},
        }
        res2 = process_message(message=msg2, sender_name="Citizen 2", db=db)
        assert mock_verify.call_count == 1  # Not called again
        assert res2.get("verdict") == "UNSIGNED"


def test_async_webhook_post_endpoint(client):
    """Test POST /api/v1/webhook/whatsapp immediately returns 200 and triggers background processing."""
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123456",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15551234567",
                                "phone_number_id": "1323651904157228",
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "Test User"},
                                    "wa_id": "919876543210",
                                }
                            ],
                            "messages": [
                                {
                                    "from": "919876543210",
                                    "id": f"wamid.async_{uuid.uuid4().hex}",
                                    "timestamp": "1710000000",
                                    "type": "text",
                                    "text": {"body": "hello"},
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }

    with patch("app.services.whatsapp_service.WhatsAppService.send_whatsapp_message") as mock_send:
        mock_send.return_value = True
        response = client.post("/api/v1/webhook/whatsapp", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "EVENT_RECEIVED"
        assert mock_send.called
