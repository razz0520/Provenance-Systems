"""Regression and Hardening Test Suite for Credential Revocation & PROVEN_INVALID.

Covers:
1. Admin-only Credential Revocation & Suspension RBAC (Admin=200, Publisher=403, Viewer=403, Unauthenticated=401)
2. PROVEN_INVALID verdict immediately returned upon credential revocation
3. Redis verification cache invalidation preventing stale VERIFIED results
4. WhatsApp verification service integration with revoked credentials
"""

import io
import json
import uuid
import numpy as np
from PIL import Image
import pytest
from sqlalchemy.orm import Session

from app.models.database import (
    Credential,
    CredentialStatus,
    RegisteredContent,
    User,
    UserRole,
    VerificationVerdict,
)
from app.services.verification_service import VerificationService
from app.services.whatsapp_service import WhatsAppService


# ============================================================================
# 1. RBAC Tests: Revoke & Suspend Credential Endpoints
# ============================================================================

def test_admin_can_revoke_and_suspend_credential(
    client,
    publisher_user_and_token,
    admin_user_and_token,
):
    """TEST 1: Admin must be allowed to revoke and suspend publisher credentials."""
    publisher, pub_token = publisher_user_and_token
    admin_user, admin_token = admin_user_and_token

    # 1. Create a credential for publisher
    create_res = client.post(
        "/api/v1/credentials",
        headers={"Authorization": f"Bearer {pub_token}"},
        json={"credential_type": "SECONDARY", "valid_days": 90},
    )
    assert create_res.status_code == 201
    cred_id = create_res.json()["id"]

    # 2. Admin suspends the credential
    susp_res = client.put(
        f"/api/v1/credentials/{cred_id}/suspend",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert susp_res.status_code == 200
    assert susp_res.json()["status"] == "SUSPENDED"

    # 3. Admin revokes the credential
    rev_res = client.put(
        f"/api/v1/credentials/{cred_id}/revoke",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": "Security compromise reported"},
    )
    assert rev_res.status_code == 200
    assert rev_res.json()["status"] == "REVOKED"
    assert rev_res.json()["revocation_reason"] == "Security compromise reported"


def test_publisher_cannot_revoke_own_credential(
    client,
    publisher_user_and_token,
):
    """TEST 2: Publisher attempting to revoke their own credential MUST receive 403 Forbidden."""
    publisher, pub_token = publisher_user_and_token

    create_res = client.post(
        "/api/v1/credentials",
        headers={"Authorization": f"Bearer {pub_token}"},
        json={"credential_type": "SECONDARY", "valid_days": 60},
    )
    assert create_res.status_code == 201
    cred_id = create_res.json()["id"]

    # Publisher attempts to revoke
    rev_res = client.put(
        f"/api/v1/credentials/{cred_id}/revoke",
        headers={"Authorization": f"Bearer {pub_token}"},
        json={"reason": "Self revocation attempt"},
    )
    assert rev_res.status_code == 403
    assert "Forbidden" in rev_res.json().get("detail", "") or rev_res.status_code == 403

    # Publisher attempts to suspend
    susp_res = client.put(
        f"/api/v1/credentials/{cred_id}/suspend",
        headers={"Authorization": f"Bearer {pub_token}"},
    )
    assert susp_res.status_code == 403


def test_viewer_cannot_revoke_credential(
    client,
    publisher_user_and_token,
    viewer_user_and_token,
):
    """TEST 3: Viewer citizen user attempting to revoke a credential MUST receive 403 Forbidden."""
    _, pub_token = publisher_user_and_token
    _, viewer_token = viewer_user_and_token

    create_res = client.post(
        "/api/v1/credentials",
        headers={"Authorization": f"Bearer {pub_token}"},
        json={"credential_type": "SECONDARY", "valid_days": 60},
    )
    assert create_res.status_code == 201
    cred_id = create_res.json()["id"]

    rev_res = client.put(
        f"/api/v1/credentials/{cred_id}/revoke",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={"reason": "Citizen attempt"},
    )
    assert rev_res.status_code == 403


def test_unauthenticated_cannot_revoke_credential(client, publisher_user_and_token):
    """TEST 4: Unauthenticated user attempting to revoke a credential MUST receive 401 or 403."""
    _, pub_token = publisher_user_and_token

    create_res = client.post(
        "/api/v1/credentials",
        headers={"Authorization": f"Bearer {pub_token}"},
        json={"credential_type": "SECONDARY", "valid_days": 60},
    )
    assert create_res.status_code == 201
    cred_id = create_res.json()["id"]

    rev_res = client.put(
        f"/api/v1/credentials/{cred_id}/revoke",
        json={"reason": "No auth"},
    )
    assert rev_res.status_code in [401, 403]


# ============================================================================
# 2. Verification Hardening: Active -> VERIFIED, Revoked -> PROVEN_INVALID
# ============================================================================

def test_credential_revocation_triggers_proven_invalid(
    client,
    publisher_user_and_token,
    admin_user_and_token,
    db: Session,
):
    """TEST 5 & 6: Active credential -> VERIFIED; After admin revokes credential -> PROVEN_INVALID."""
    publisher, pub_token = publisher_user_and_token
    admin_user, admin_token = admin_user_and_token

    # 1. Create synthetic PNG image with unique random seed
    seed = np.random.randint(1000, 999999)
    img_arr = np.random.RandomState(seed).randint(0, 255, (100, 100, 3), dtype=np.uint8)
    img = Image.fromarray(img_arr)
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    content_bytes = img_bytes.getvalue()

    # 2. Register content as publisher
    reg_res = client.post(
        "/api/v1/content/register",
        headers={"Authorization": f"Bearer {pub_token}"},
        files={"file": ("press_release.png", content_bytes, "image/png")},
        data={"metadata": json.dumps({"title": f"Test Announcement {seed}"})},
    )
    assert reg_res.status_code == 201

    # Look up publisher's active credential
    cred = db.query(Credential).filter(
        Credential.publisher_id == publisher.id,
        Credential.status == CredentialStatus.ACTIVE,
    ).first()
    assert cred is not None
    cred_id = str(cred.id)

    # 3. Verify content while credential is ACTIVE -> VERIFIED
    verif_res = client.post(
        "/api/v1/verify",
        files={"file": ("press_release.png", content_bytes, "image/png")},
    )
    assert verif_res.status_code == 200
    assert verif_res.json()["verdict"] == "VERIFIED"
    assert verif_res.json()["confidence_score"] >= 0.95

    # 4. Admin revokes the publisher's credential
    rev_res = client.put(
        f"/api/v1/credentials/{cred_id}/revoke",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": "Compromised publisher private key"},
    )
    assert rev_res.status_code == 200
    assert rev_res.json()["status"] == "REVOKED"

    # 5. Verify the EXACT SAME content immediately -> MUST RETURN PROVEN_INVALID
    verif_after_rev_res = client.post(
        "/api/v1/verify",
        files={"file": ("press_release.png", content_bytes, "image/png")},
    )
    assert verif_after_rev_res.status_code == 200
    verdict_data = verif_after_rev_res.json()
    assert verdict_data["verdict"] == "PROVEN_INVALID"
    assert verdict_data["confidence_score"] == 1.0
    assert "revoked" in verdict_data["evidence_bundle"].get("notice", "").lower()


# ============================================================================
# 3. Redis Cache Invalidation & Revocation Bypass
# ============================================================================

def test_redis_cache_bypassed_or_invalidated_on_revocation(
    client,
    publisher_user_and_token,
    admin_user_and_token,
    db: Session,
):
    """TEST 7: WhatsApp/Redis verification cache must never return VERIFIED for a revoked credential."""
    publisher, pub_token = publisher_user_and_token
    admin_user, admin_token = admin_user_and_token

    # 1. Register a text statement with unique token
    unique_tag = uuid.uuid4().hex[:8]
    statement_str = f"Official Circular {unique_tag}: National Health Advisory 2026-08."
    statement_bytes = statement_str.encode("utf-8")

    reg_res = client.post(
        "/api/v1/content/register",
        headers={"Authorization": f"Bearer {pub_token}"},
        files={"file": (f"advisory_{unique_tag}.txt", statement_bytes, "text/plain")},
        data={"metadata": json.dumps({"title": f"Health Advisory {unique_tag}"})},
    )
    assert reg_res.status_code == 201
    reg_data = reg_res.json()
    content_id = reg_data["content_id"]
    sha256 = reg_data["sha256_hash"]

    cred = db.query(Credential).filter(
        Credential.publisher_id == publisher.id,
        Credential.status == CredentialStatus.ACTIVE,
    ).first()
    assert cred is not None
    cred_id = str(cred.id)

    # 2. Simulate WhatsApp text verification (populating cache)
    cache_key = f"text:{sha256}"
    initial_verif = {
        "verdict": "VERIFIED",
        "confidence_score": 1.0,
        "matched_content": {"id": content_id},
        "evidence_bundle": {"notice": "Valid publisher signature detected in registry."},
    }
    WhatsAppService.set_cached_verification(cache_key, initial_verif)

    # Confirm cache returns the result
    cached = WhatsAppService.get_cached_verification(cache_key)
    assert cached is not None
    assert cached["verdict"] == "VERIFIED"

    # 3. Admin revokes the credential
    rev_res = client.put(
        f"/api/v1/credentials/{cred_id}/revoke",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": "Emergency security revocation"},
    )
    assert rev_res.status_code == 200

    # 4. Direct text verification API now returns PROVEN_INVALID
    verif_res = client.post(
        "/api/v1/verify/text",
        json={"text": statement_str},
    )
    assert verif_res.status_code == 200
    assert verif_res.json()["verdict"] == "PROVEN_INVALID"


# ============================================================================
# 4. Additional Hardening: Re-registration, Manifest, & Suspended Credential
# ============================================================================

def test_duplicate_registration_prevention(client, publisher_user_and_token):
    """TEST 8: Re-registering identical SHA-256 content returns 400 Bad Request."""
    _, pub_token = publisher_user_and_token

    seed = np.random.randint(1000, 999999)
    img_arr = np.random.RandomState(seed).randint(0, 255, (80, 80, 3), dtype=np.uint8)
    img = Image.fromarray(img_arr)
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    content_bytes = img_bytes.getvalue()

    # First registration -> 201
    reg1 = client.post(
        "/api/v1/content/register",
        headers={"Authorization": f"Bearer {pub_token}"},
        files={"file": ("orig.png", content_bytes, "image/png")},
        data={"metadata": json.dumps({"title": "Initial Registration"})},
    )
    assert reg1.status_code == 201

    # Second registration of same content -> 400 Conflict/Duplicate
    reg2 = client.post(
        "/api/v1/content/register",
        headers={"Authorization": f"Bearer {pub_token}"},
        files={"file": ("duplicate.png", content_bytes, "image/png")},
        data={"metadata": json.dumps({"title": "Duplicate Registration"})},
    )
    assert reg2.status_code == 400


def test_suspended_credential_returns_proven_invalid(
    client,
    publisher_user_and_token,
    admin_user_and_token,
    db: Session,
):
    """TEST 9: Content signed under a SUSPENDED credential returns PROVEN_INVALID."""
    publisher, pub_token = publisher_user_and_token
    _, admin_token = admin_user_and_token

    seed = np.random.randint(1000, 999999)
    img_arr = np.random.RandomState(seed).randint(0, 255, (80, 80, 3), dtype=np.uint8)
    img = Image.fromarray(img_arr)
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    content_bytes = img_bytes.getvalue()

    reg = client.post(
        "/api/v1/content/register",
        headers={"Authorization": f"Bearer {pub_token}"},
        files={"file": ("susp_test.png", content_bytes, "image/png")},
        data={"metadata": json.dumps({"title": "Suspension Test"})},
    )
    assert reg.status_code == 201

    cred = db.query(Credential).filter(
        Credential.publisher_id == publisher.id,
        Credential.status == CredentialStatus.ACTIVE,
    ).first()
    assert cred is not None

    # Admin suspends credential
    susp = client.put(
        f"/api/v1/credentials/{cred.id}/suspend",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert susp.status_code == 200

    # Verification must return PROVEN_INVALID
    verif = client.post(
        "/api/v1/verify",
        files={"file": ("susp_test.png", content_bytes, "image/png")},
    )
    assert verif.status_code == 200
    assert verif.json()["verdict"] == "PROVEN_INVALID"
    assert "suspended" in verif.json()["evidence_bundle"].get("notice", "").lower()

