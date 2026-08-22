import io
import json
import os
import uuid
import numpy as np
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.database import SessionLocal, engine
from app.main import app
from app.models import DomainWhitelist, User, UserRole
from app.services.auth_service import register_admin, register_publisher


@pytest.fixture
def client():
    """Create test client for FastAPI."""
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


@pytest.fixture
def publisher_user_and_token(db):
    """Fixture providing an authenticated publisher and Bearer token."""
    email = f"pub_api_{uuid.uuid4().hex[:6]}@pib.gov.in"
    user = register_publisher(
        db=db,
        email=email,
        password="PublisherPassword#123",
        organization_name="Press Bureau",
        organization_domain="pib.gov.in",
    )
    token = create_access_token(user.id, UserRole.PUBLISHER)
    return user, token


@pytest.fixture
def admin_user_and_token(db):
    """Fixture providing an authenticated admin and Bearer token."""
    email = f"admin_api_{uuid.uuid4().hex[:6]}@gov.in"
    user = register_admin(
        db=db,
        email=email,
        password="AdminPassword#123",
    )
    token = create_access_token(user.id, UserRole.ADMIN)
    return user, token


# ============================================================================
# 1. System & Health Endpoint Tests
# ============================================================================

def test_health_and_root(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ["ok", "degraded"]
    assert "database" in data
    assert "redis" in data

    res_root = client.get("/")
    assert res_root.status_code == 200
    assert "Deepfake" in res_root.json()["title"]


def test_system_status_and_integrity(client):
    res_status = client.get("/api/v1/status")
    assert res_status.status_code == 200
    data = res_status.json()
    assert "active_publishers" in data
    assert "registry_integrity" in data

    res_integ = client.get("/api/v1/registry/integrity")
    assert res_integ.status_code == 200
    integ_data = res_integ.json()
    assert integ_data["is_valid"] is True
    assert "genesis_hash" in integ_data


# ============================================================================
# 2. Auth Endpoints Tests
# ============================================================================

def test_auth_register_and_login_flow(client):
    email = f"register_flow_{uuid.uuid4().hex[:6]}@pib.gov.in"
    pw = "SecurePassword#2026"

    # Register
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": pw,
            "organization_name": "Ministry of Information",
            "organization_domain": "pib.gov.in",
        },
    )
    assert reg_res.status_code == 201
    user_data = reg_res.json()
    assert user_data["email"] == email
    assert user_data["role"] == "PUBLISHER"

    # Login
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": pw},
    )
    assert login_res.status_code == 200
    tokens = login_res.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens

    # Refresh
    ref_res = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert ref_res.status_code == 200
    new_tokens = ref_res.json()
    assert "access_token" in new_tokens

    # Logout
    logout_res = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {new_tokens['access_token']}"},
    )
    assert logout_res.status_code == 200
    assert logout_res.json()["success"] is True


def test_google_auth_url(client):
    res = client.get("/api/v1/auth/google")
    assert res.status_code == 200
    assert "accounts.google.com" in res.json()["url"]


# ============================================================================
# 3. Content Registration & Verification Pipeline Tests
# ============================================================================

def test_content_registration_and_verification_pipeline(client, publisher_user_and_token):
    publisher, token = publisher_user_and_token

    # Create synthetic test image with texture
    img_arr = np.random.RandomState(42).randint(0, 255, (120, 120, 3), dtype=np.uint8)
    img = Image.fromarray(img_arr)
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="PNG")
    img_bytes = img_byte_arr.getvalue()

    # Step 1: Register content as Publisher
    reg_res = client.post(
        "/api/v1/content/register",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("press_release_image.png", img_bytes, "image/png")},
        data={"metadata": json.dumps({"title": "Official Announcement 2026"})},
    )

    assert reg_res.status_code == 201
    content_data = reg_res.json()
    content_id = content_data["content_id"]
    sha256 = content_data["sha256_hash"]
    assert len(sha256) == 64
    assert content_data["hash_chain_block_id"] > 0

    # Step 2: Get content details
    get_res = client.get(f"/api/v1/content/{content_id}")
    assert get_res.status_code == 200
    assert get_res.json()["sha256_hash"] == sha256

    # Step 3: Verify exact original file -> Should be VERIFIED
    verify_res = client.post(
        "/api/v1/verify",
        files={"file": ("citizen_upload.png", img_bytes, "image/png")},
    )
    assert verify_res.status_code == 200
    v_data = verify_res.json()
    assert v_data["verdict"] == "VERIFIED"
    assert v_data["confidence_score"] == 1.0
    assert v_data["evidence_bundle"]["signature_valid"] is True
    assert v_data["evidence_bundle"]["chain_integrity"] is True
    verification_id = v_data["verification_id"]

    # Step 4: Retrieve past verification result
    get_v_res = client.get(f"/api/v1/verify/{verification_id}")
    assert get_v_res.status_code == 200
    assert get_v_res.json()["verdict"] == "VERIFIED"

    # Step 5: Verify an unregistered file -> Should be UNSIGNED
    fake_arr = np.random.RandomState(999).randint(0, 255, (120, 120, 3), dtype=np.uint8)
    fake_img = Image.fromarray(fake_arr)
    fake_bytes = io.BytesIO()
    fake_img.save(fake_bytes, format="PNG")

    unregistered_res = client.post(
        "/api/v1/verify",
        files={"file": ("unregistered.png", fake_bytes.getvalue(), "image/png")},
    )
    assert unregistered_res.status_code == 200
    assert unregistered_res.json()["verdict"] in ["UNSIGNED", "SUSPICIOUS"]


def test_text_verification_endpoint(client, publisher_user_and_token):
    publisher, token = publisher_user_and_token

    # Register text file
    official_statement = b"Official Government Gazette: National Holiday on August 22, 2026."
    reg_res = client.post(
        "/api/v1/content/register",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("gazette.txt", official_statement, "text/plain")},
    )
    assert reg_res.status_code == 201

    # Verify matching text
    v_res = client.post(
        "/api/v1/verify/text",
        json={"text": "Official Government Gazette: National Holiday on August 22, 2026."},
    )
    assert v_res.status_code == 200
    assert v_res.json()["verdict"] == "VERIFIED"


# ============================================================================
# 4. Credential & Admin Operations Tests
# ============================================================================

def test_credentials_and_admin_endpoints(client, publisher_user_and_token, admin_user_and_token):
    _, pub_token = publisher_user_and_token
    admin_user, admin_token = admin_user_and_token

    # List credentials
    cred_list_res = client.get(
        "/api/v1/credentials",
        headers={"Authorization": f"Bearer {pub_token}"},
    )
    assert cred_list_res.status_code == 200
    assert len(cred_list_res.json()) >= 1

    # Create secondary credential
    new_cred_res = client.post(
        "/api/v1/credentials",
        headers={"Authorization": f"Bearer {pub_token}"},
        json={"credential_type": "SECONDARY", "valid_days": 180},
    )
    assert new_cred_res.status_code == 201
    cred_id = new_cred_res.json()["id"]

    # Suspend credential
    susp_res = client.put(
        f"/api/v1/credentials/{cred_id}/suspend",
        headers={"Authorization": f"Bearer {pub_token}"},
    )
    assert susp_res.status_code == 200
    assert susp_res.json()["status"] == "SUSPENDED"

    # Revoke credential
    rev_res = client.put(
        f"/api/v1/credentials/{cred_id}/revoke",
        headers={"Authorization": f"Bearer {pub_token}"},
        json={"reason": "Key rotation requested"},
    )
    assert rev_res.status_code == 200
    assert rev_res.json()["status"] == "REVOKED"

    # Admin: List users
    users_res = client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert users_res.status_code == 200
    assert len(users_res.json()) >= 2

    # Admin: View audit logs
    audit_res = client.get(
        "/api/v1/admin/audit-logs",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert audit_res.status_code == 200
    assert len(audit_res.json()) > 0

    # Admin: System stats
    stats_res = client.get(
        "/api/v1/admin/stats",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert stats_res.status_code == 200
    assert stats_res.json()["total_users"] > 0
    assert stats_res.json()["chain_integrity_valid"] is True
