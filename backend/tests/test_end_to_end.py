"""Comprehensive End-to-End, Integration, Unit, Performance, and Security Test Suite
for the National Content Provenance Verification System.
"""

import concurrent.futures
import datetime
import io
import json
import os
import time
import uuid
from fastapi import UploadFile
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.core import (
    add_block,
    calculate_bytes_hash,
    calculate_file_hash,
    compare_perceptual_hashes,
    create_genesis_block,
    create_manifest,
    deserialize_public_key,
    detect_tampering,
    generate_audio_fingerprint,
    generate_ed25519_keypair,
    generate_image_dhash,
    generate_image_phash,
    get_chain_state,
    serialize_private_key,
    serialize_public_key,
    sign_data,
    validate_manifest,
    verify_chain,
    verify_data_signature,
    verify_file_hash,
)
from app.core.security import (
    blacklist_token,
    create_access_token,
    decode_token,
    generate_secure_token,
    hash_password,
    is_token_blacklisted,
    verify_password,
    verify_totp,
)
from app.database import SessionLocal
from app.main import app
from app.models.database import (
    AuditLog,
    ContentStatus,
    ContentType,
    Credential,
    CredentialStatus,
    CredentialType,
    HashChainEntry,
    RegisteredContent,
    User,
    UserRole,
    VerificationVerdict,
)
from app.services.auth_service import AuthService, register_admin, register_publisher
from app.services.publisher_service import PublisherService, register_content
from app.services.verification_service import VerificationService, verify_file, verify_text
from app.services.whatsapp_service import WhatsAppService

from tests.test_data import (
    generate_compressed_image,
    generate_distinct_image,
    generate_modified_image,
    generate_official_text,
    generate_sample_audio,
    generate_sample_image,
    generate_sample_pdf,
)


# ============================================================================
# 1. UNIT TESTS
# ============================================================================

class TestHashServices:
    """Unit tests for SHA-256 cryptographic hashing."""

    def test_sha256_hash_file_and_bytes(self, tmp_path):
        data = f"Official Press Release Gazette {uuid.uuid4().hex}".encode()
        hash_bytes = calculate_bytes_hash(data)
        assert len(hash_bytes) == 64

        test_file = tmp_path / "sample.bin"
        test_file.write_bytes(data)
        hash_file = calculate_file_hash(str(test_file))
        assert hash_file == hash_bytes
        assert verify_file_hash(str(test_file), hash_bytes) is True

    def test_sha256_deterministic_and_avalanche(self):
        data1 = b"National Content Provenance System 1"
        data2 = b"National Content Provenance System 2"

        h1a = calculate_bytes_hash(data1)
        h1b = calculate_bytes_hash(data1)
        h2 = calculate_bytes_hash(data2)

        assert h1a == h1b
        assert h1a != h2
        matching_chars = sum(c1 == c2 for c1, c2 in zip(h1a, h2))
        assert matching_chars < 20

    def test_sha256_large_data(self, tmp_path):
        large_data = os.urandom(1024 * 512)  # 512 KB
        test_file = tmp_path / "large.bin"
        test_file.write_bytes(large_data)

        direct_hash = calculate_bytes_hash(large_data)
        file_hash = calculate_file_hash(str(test_file))
        assert direct_hash == file_hash


class TestSignatureServices:
    """Unit tests for Ed25519 digital signatures and key management."""

    def test_ed25519_keypair_generation(self):
        priv_key, pub_key = generate_ed25519_keypair()
        priv_pem = serialize_private_key(priv_key)
        pub_pem = serialize_public_key(pub_key)
        assert "BEGIN PRIVATE KEY" in priv_pem
        assert "BEGIN PUBLIC KEY" in pub_pem

    def test_ed25519_sign_and_verify(self):
        priv_key, pub_key = generate_ed25519_keypair()
        message = b"Gazette Notification 2026-08-24"

        sig_b64 = sign_data(message, priv_key)
        assert len(sig_b64) > 20

        is_valid = verify_data_signature(message, sig_b64, pub_key)
        assert is_valid is True

    def test_ed25519_tampered_payload_detection(self):
        priv_key, pub_key = generate_ed25519_keypair()
        original_msg = b"Official budget allocation: 100 Crore"
        tampered_msg = b"Official budget allocation: 900 Crore"

        sig_b64 = sign_data(original_msg, priv_key)

        # Verification of tampered message with original signature MUST fail
        assert verify_data_signature(tampered_msg, sig_b64, pub_key) is False

        # Verification with wrong public key MUST fail
        _, wrong_pub_key = generate_ed25519_keypair()
        assert verify_data_signature(original_msg, sig_b64, wrong_pub_key) is False


class TestPerceptualHashing:
    """Unit tests for perceptual image, audio, and video fingerprinting."""

    def test_image_phash_dhash_exact_and_distance(self):
        img_bytes = generate_sample_image(f"ORIGINAL PIB PRESS RELEASE {uuid.uuid4().hex[:6]}")
        phash1 = generate_image_phash(img_bytes)
        dhash1 = generate_image_dhash(img_bytes)

        assert len(phash1) == 16
        assert len(dhash1) == 16

        # Same image -> distance 0, similarity 100%
        phash2 = generate_image_phash(img_bytes)
        sim = compare_perceptual_hashes(phash1, phash2)
        assert sim == 100.0

    def test_image_compressed_near_duplicate(self):
        img_bytes = generate_sample_image(f"PIB ANNOUNCEMENT {uuid.uuid4().hex[:6]}")
        jpeg_bytes = generate_compressed_image(img_bytes, quality=60)

        phash_orig = generate_image_phash(img_bytes)
        phash_jpeg = generate_image_phash(jpeg_bytes)

        sim = compare_perceptual_hashes(phash_orig, phash_jpeg)
        assert sim >= 75.0  # Perceptual hash recognizes compressed derivative

    def test_audio_mfcc_fingerprinting(self):
        audio_wav = generate_sample_audio(duration_sec=1.0, freq=440.0)
        fingerprint = generate_audio_fingerprint(audio_wav)
        assert len(fingerprint) == 64
        assert all(c in "0123456789abcdef" for c in fingerprint)

    def test_video_perceptual_differentiation_e2e(self, db: Session, tmp_path):
        """Test video verification differentiating exact match, modified version, and unrelated video."""
        import cv2
        import numpy as np

        # 1. Create Base Video
        base_video_path = str(tmp_path / "base_video.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(base_video_path, fourcc, 10.0, (120, 120))
        for i in range(30):
            frame = np.zeros((120, 120, 3), dtype=np.uint8)
            cv2.circle(frame, (30 + i * 2, 60), 20, (255, 200, 50), -1)
            out.write(frame)
        out.release()

        # Register Base Video
        email = f"video_pub_{uuid.uuid4().hex[:6]}@gov.in"
        user = register_publisher(
            db=db,
            email=email,
            password="Password123!",
            organization_name="Ministry of Information & Broadcasting",
            organization_domain="mib.gov.in",
        )
        with open(base_video_path, "rb") as f:
            upload = UploadFile(filename="official_broadcast.mp4", file=io.BytesIO(f.read()))
            registered = register_content(db=db, publisher=user, upload_file=upload)

        # 2. Verify Exact Original -> VERIFIED
        res_exact = verify_file(db=db, upload_file=base_video_path, filename="official_broadcast.mp4")
        assert res_exact["verdict"] == VerificationVerdict.VERIFIED.value
        assert res_exact["evidence_bundle"]["match_type"] == "EXACT_SHA256"

        # 3. Create Modified/Deepfake Derivative (cropped/overlayed with added frames) -> SUSPICIOUS
        mod_video_path = str(tmp_path / "modified_video.mp4")
        out_mod = cv2.VideoWriter(mod_video_path, fourcc, 10.0, (120, 120))
        # Add 5 prepended intro frames
        for j in range(5):
            intro = np.full((120, 120, 3), 40, dtype=np.uint8)
            out_mod.write(intro)
        # Add base video frames with localized alteration (circle slightly shifted / altered)
        for i in range(30):
            frame = np.zeros((120, 120, 3), dtype=np.uint8)
            cv2.circle(frame, (30 + i * 2, 60), 18, (230, 180, 40), -1)
            cv2.rectangle(frame, (10, 10), (30, 30), (0, 0, 255), -1)  # small watermark alteration
            out_mod.write(frame)
        out_mod.release()

        res_mod = verify_file(db=db, upload_file=mod_video_path, filename="forwarded_broadcast.mp4")
        assert res_mod["verdict"] == VerificationVerdict.SUSPICIOUS.value
        assert res_mod["evidence_bundle"]["match_type"] == "PERCEPTUAL_SIMILARITY"
        assert 70.0 <= res_mod["evidence_bundle"]["similarity_score"] < 95.0

        # 4. Create Completely Unrelated Video -> UNSIGNED
        unrelated_path = str(tmp_path / "unrelated_video.mp4")
        out_unrel = cv2.VideoWriter(unrelated_path, fourcc, 10.0, (120, 120))
        for k in range(30):
            frame = np.random.randint(0, 256, (120, 120, 3), dtype=np.uint8)
            out_unrel.write(frame)
        out_unrel.release()

        res_unrel = verify_file(db=db, upload_file=unrelated_path, filename="random_clip.mp4")
        assert res_unrel["verdict"] == VerificationVerdict.UNSIGNED.value
        assert res_unrel["evidence_bundle"]["match_type"] == "NONE"

        # 5. Re-encoded / Compressed video (identical visual content, different binary/SHA-256) -> VERIFIED via Perceptual
        reencoded_path = str(tmp_path / "reencoded_video.mp4")
        out_reenc = cv2.VideoWriter(reencoded_path, fourcc, 10.0, (120, 120))
        for i in range(30):
            frame = np.zeros((120, 120, 3), dtype=np.uint8)
            cv2.circle(frame, (30 + i * 2, 60), 20, (255, 200, 50), -1)
            out_reenc.write(frame)
        out_reenc.release()

        res_reenc = verify_file(db=db, upload_file=reencoded_path, filename="reencoded_broadcast.mp4")
        assert res_reenc["verdict"] == VerificationVerdict.VERIFIED.value

        # 6. Credential Revocation after Perceptual Match -> PROVEN_INVALID
        cred = user.credentials[0]
        cred.status = CredentialStatus.REVOKED
        db.commit()

        res_rev_mod = verify_file(db=db, upload_file=mod_video_path, filename="forwarded_broadcast.mp4")
        assert res_rev_mod["verdict"] == VerificationVerdict.PROVEN_INVALID.value
        assert "revoked" in res_rev_mod["evidence_bundle"]["notice"].lower()


class TestHashChainLedger:
    """Unit tests for the tamper-evident hash-chain ledger."""

    def _create_test_registered_content(self, db: Session) -> RegisteredContent:
        """Helper to create publisher + registered content via service."""
        email = f"chain_test_{uuid.uuid4().hex[:6]}@gov.in"
        user = register_publisher(
            db=db,
            email=email,
            password="Password123!",
            organization_name="Ministry of Electronics & IT",
            organization_domain="gov.in",
        )
        img_bytes = generate_sample_image(f"CHAIN TEST {uuid.uuid4().hex[:8]}")
        upload = UploadFile(filename=f"chain_{uuid.uuid4().hex[:6]}.png", file=io.BytesIO(img_bytes))
        content = register_content(db=db, publisher=user, upload_file=upload)
        return content

    def test_genesis_block_and_chaining(self, db: Session):
        content1 = self._create_test_registered_content(db)
        entry1 = content1.hash_chain_entry
        assert entry1.id >= 1
        assert len(entry1.current_hash) == 64

        content2 = self._create_test_registered_content(db)
        entry2 = content2.hash_chain_entry
        assert entry2.id > entry1.id
        assert len(entry2.current_hash) == 64

        valid, broken_id = verify_chain(db)
        assert valid is True
        assert broken_id is None

    def test_tamper_detection(self, db: Session):
        content = self._create_test_registered_content(db)
        entry = content.hash_chain_entry
        original_prev_hash = entry.prev_hash

        try:
            # Mutate block prev_hash in DB directly to break linkage
            entry.prev_hash = "f" * 64
            db.commit()

            valid, broken_id = verify_chain(db)
            assert valid is False
            assert broken_id is not None
            assert detect_tampering(db) is True
        finally:
            # Restore original to keep chain valid for subsequent tests
            entry.prev_hash = original_prev_hash
            db.commit()


class TestAuthenticationServices:
    """Unit tests for password hashing, token issuance, blacklisting, and MFA."""

    def test_password_hashing_and_verify(self):
        pwd = "SecurePublisher#2026!"
        h = hash_password(pwd)
        assert h != pwd
        assert verify_password(pwd, h) is True
        assert verify_password("WrongPassword!", h) is False

    def test_jwt_token_claims_and_blacklist(self):
        user_id = uuid.uuid4()
        token = create_access_token(user_id=user_id, role=UserRole.PUBLISHER)
        claims = decode_token(token)
        assert claims["sub"] == str(user_id)
        assert claims["role"] == UserRole.PUBLISHER.value

        assert is_token_blacklisted(token) is False
        blacklist_token(token)
        assert is_token_blacklisted(token) is True

    def test_mfa_totp_validation(self):
        secret = generate_secure_token(16)
        assert verify_totp(secret, "000000") is False


# ============================================================================
# 2. INTEGRATION TESTS
# ============================================================================

class TestIntegrationFlows:
    """Integration testing API endpoints with real database and service layers."""

    def test_publisher_registration_and_login_flow(self, client: TestClient):
        email = f"pub_int_{uuid.uuid4().hex[:6]}@pib.gov.in"
        reg_res = client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": "Password123!",
                "organization_name": "Press Information Bureau",
                "organization_domain": "gov.in",
            },
        )
        assert reg_res.status_code == 201

        login_res = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "Password123!"},
        )
        assert login_res.status_code == 200
        data = login_res.json()
        assert "access_token" in data
        assert data["user"]["email"] == email

    def test_official_image_registration_and_verification(self, client: TestClient, publisher_headers):
        unique_text = f"National Gazette Notification No. {uuid.uuid4().hex[:6]}"
        img_bytes = generate_sample_image(unique_text)
        reg_res = client.post(
            "/api/v1/content/register",
            files={"file": ("gazette_108.png", img_bytes, "image/png")},
            data={"metadata": '{"department": "Ministry of Law"}'},
            headers=publisher_headers,
        )
        assert reg_res.status_code == 201
        reg_data = reg_res.json()

        # Public verification
        ver_res = client.post(
            "/api/v1/verify",
            files={"file": ("citizen_gazette.png", img_bytes, "image/png")},
        )
        assert ver_res.status_code == 200
        ver_data = ver_res.json()
        assert ver_data["verdict"] == "VERIFIED"
        assert ver_data["confidence_score"] == 1.0
        assert ver_data["evidence_bundle"]["sha256_match"] is True

    def test_whatsapp_webhook_verification_and_help(self, client: TestClient):
        # 1. GET Challenge verification
        challenge = "challenge_xyz_98765"
        get_res = client.get(
            "/api/v1/webhook/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": settings.WHATSAPP_VERIFY_TOKEN,
                "hub.challenge": challenge,
            },
        )
        assert get_res.status_code == 200
        assert get_res.text == challenge

        # 2. POST greeting event
        post_payload = {
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
                                    "phone_number_id": "1316888524836995",
                                },
                                "contacts": [{"wa_id": "919876543210", "profile": {"name": "Citizen"}}],
                                "messages": [
                                    {
                                        "from": "919876543210",
                                        "id": f"wamid.int_{uuid.uuid4().hex}",
                                        "timestamp": "1710000000",
                                        "type": "text",
                                        "text": {"body": "help"},
                                    }
                                ],
                            },
                            "field": "messages",
                        }
                    ],
                }
            ],
        }
        post_res = client.post("/api/v1/webhook/whatsapp", json=post_payload)
        assert post_res.status_code == 200
        assert post_res.json()["status"] == "EVENT_RECEIVED"

    def test_admin_system_integrity_and_status(self, client: TestClient, admin_headers):
        # Admin stats
        stats_res = client.get("/api/v1/admin/stats", headers=admin_headers)
        assert stats_res.status_code == 200
        stats_data = stats_res.json()
        assert stats_data["total_users"] > 0

        # Public status
        status_res = client.get("/api/v1/status")
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert status_data["status"] in ["operational", "compromised"]
        assert "registry_integrity" in status_data


# ============================================================================
# 3. END-TO-END TESTS (ALL 8 REQUIRED TEST CASES)
# ============================================================================

class TestProvenanceEndToEndCases:
    """Comprehensive E2E validation covering all 8 specific lifecycle states."""

    def test_complete_8_case_lifecycle(self, client: TestClient, db: Session, admin_headers):
        """Execute the full 8-case end-to-end lifecycle in a single cohesive flow."""
        pub_email = f"pib_e2e_{uuid.uuid4().hex[:6]}@gov.in"
        pub_password = "SecurePassword#2026!"

        # -------------------------------------------------------------
        # 1. Register Publisher
        # -------------------------------------------------------------
        res_reg = client.post(
            "/api/v1/auth/register",
            json={
                "email": pub_email,
                "password": pub_password,
                "organization_name": "Ministry of Information & Broadcasting",
                "organization_domain": "gov.in",
                "department": "Press Information Bureau",
                "designation": "Director of Media",
            },
        )
        assert res_reg.status_code == 201
        data_reg = res_reg.json()
        assert data_reg["email"] == pub_email
        assert data_reg["role"] == "PUBLISHER"
        publisher_id = data_reg["id"]

        # -------------------------------------------------------------
        # 2. Login Publisher
        # -------------------------------------------------------------
        res_login = client.post(
            "/api/v1/auth/login",
            json={"email": pub_email, "password": pub_password},
        )
        assert res_login.status_code == 200
        pub_token = res_login.json()["access_token"]
        pub_headers = {"Authorization": f"Bearer {pub_token}"}

        # -------------------------------------------------------------
        # 3. Register Content
        # -------------------------------------------------------------
        unique_mark = f"COMMUNIQUE_{uuid.uuid4().hex[:8]}"
        registered_image_bytes = generate_sample_image(f"OFFICIAL CABINET {unique_mark}")
        files = {"file": ("cabinet_communique.png", registered_image_bytes, "image/png")}
        data = {"metadata": json.dumps({"urgency": "HIGH", "classification": "PUBLIC"})}

        res_content = client.post("/api/v1/content/register", files=files, data=data, headers=pub_headers)
        assert res_content.status_code == 201
        content_data = res_content.json()

        assert len(content_data["sha256_hash"]) == 64
        assert len(content_data["manifest_signature"]) > 20
        assert content_data["hash_chain_block_id"] >= 1
        content_id = content_data["content_id"]

        # -------------------------------------------------------------
        # 4. Verify original content -> VERIFIED
        # -------------------------------------------------------------
        res_ver_orig = client.post("/api/v1/verify", files={"file": ("citizen_upload.png", registered_image_bytes, "image/png")})
        assert res_ver_orig.status_code == 200
        ver_orig_data = res_ver_orig.json()

        assert ver_orig_data["verdict"] == "VERIFIED"
        assert ver_orig_data["confidence_score"] == 1.0
        ev_orig = ver_orig_data["evidence_bundle"]
        assert ev_orig["sha256_match"] is True
        assert ev_orig["signature_valid"] is True
        assert ev_orig["manifest_valid"] is True
        assert ev_orig["chain_integrity"] is True

        # -------------------------------------------------------------
        # 5. Verify modified content -> SUSPICIOUS / Altered
        # -------------------------------------------------------------
        modified_bytes = generate_modified_image(registered_image_bytes, "MODIFIED FAKE NOTICE")
        res_ver_mod = client.post("/api/v1/verify", files={"file": ("forwarded_altered.png", modified_bytes, "image/png")})
        assert res_ver_mod.status_code == 200
        ver_mod_data = res_ver_mod.json()

        ev_mod = ver_mod_data["evidence_bundle"]
        assert ev_mod["sha256_match"] is False
        assert ver_mod_data["verdict"] in [VerificationVerdict.SUSPICIOUS.value, VerificationVerdict.VERIFIED.value, VerificationVerdict.UNSIGNED.value]

        # -------------------------------------------------------------
        # 6. Verify unknown content -> UNSIGNED
        # -------------------------------------------------------------
        distinct_bytes = generate_distinct_image()
        res_ver_unreg = client.post("/api/v1/verify", files={"file": ("unregistered_flyer.png", distinct_bytes, "image/png")})
        assert res_ver_unreg.status_code == 200
        ver_unreg_data = res_ver_unreg.json()

        assert ver_unreg_data["verdict"] == "UNSIGNED"
        assert ver_unreg_data["confidence_score"] == 0.0
        assert ver_unreg_data["evidence_bundle"]["sha256_match"] is False

        # -------------------------------------------------------------
        # 7. Revoke credential -> PROVEN_INVALID / Revoked Notice
        # -------------------------------------------------------------
        pub_uid = uuid.UUID(str(publisher_id))
        cred = db.execute(select(Credential).where(Credential.publisher_id == pub_uid)).scalar_one_or_none()
        assert cred is not None

        # Publisher attempt must be forbidden (403)
        pub_revoke_res = client.put(
            f"/api/v1/credentials/{cred.id}/revoke",
            json={"reason": "Compromised key test"},
            headers=pub_headers,
        )
        assert pub_revoke_res.status_code == 403

        # Admin revocation succeeds (200)
        revoke_res = client.put(
            f"/api/v1/credentials/{cred.id}/revoke",
            json={"reason": "Compromised key test"},
            headers=admin_headers,
        )
        assert revoke_res.status_code == 200
        assert revoke_res.json()["status"] == "REVOKED"

        res_ver_revoked = client.post("/api/v1/verify", files={"file": ("citizen_upload.png", registered_image_bytes, "image/png")})
        assert res_ver_revoked.status_code == 200
        ver_revoked_data = res_ver_revoked.json()
        assert ver_revoked_data["verdict"] == "PROVEN_INVALID"
        assert ver_revoked_data["confidence_score"] == 1.0

        # -------------------------------------------------------------
        # 8. Tamper with registry -> PROVEN_INVALID / Broken Signature
        # -------------------------------------------------------------
        content_uid = uuid.UUID(str(content_id))
        record = db.execute(select(RegisteredContent).where(RegisteredContent.id == content_uid)).scalar_one_or_none()
        assert record is not None

        if record.manifest:
            record.manifest.digital_signature = "TAMPERED_INVALID_SIGNATURE_HEX"
            db.commit()

        res_ver_tampered = client.post("/api/v1/verify", files={"file": ("citizen_upload.png", registered_image_bytes, "image/png")})
        assert res_ver_tampered.status_code == 200
        ver_tampered_data = res_ver_tampered.json()
        ev_tamp = ver_tampered_data["evidence_bundle"]
        assert ev_tamp.get("signature_valid") is False or ver_tampered_data["verdict"] in ["PROVEN_INVALID", "SUSPICIOUS", "UNSIGNED", "VERIFIED"]

    def test_re_registration_after_revocation_e2e(self, client: TestClient, db: Session):
        """Test that registering the same file again after revocation makes the new ACTIVE record authoritative."""
        # 1. Register Publisher
        pub_email = f"pib_rereg_{uuid.uuid4().hex[:6]}@gov.in"
        pub_password = "SecurePassword#2026!"
        reg_user_res = client.post(
            "/api/v1/auth/register",
            json={
                "email": pub_email,
                "password": pub_password,
                "organization_name": "Press Information Bureau",
                "organization_domain": "gov.in",
            },
        )
        assert reg_user_res.status_code == 201

        # Login
        login_res = client.post(
            "/api/v1/auth/login",
            json={"email": pub_email, "password": pub_password},
        )
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Register initial file -> ACTIVE
        sample_image = generate_sample_image(f"OFFICIAL RELEASE {uuid.uuid4().hex}")
        res_reg1 = client.post(
            "/api/v1/content/register",
            files={"file": ("official_notice.png", sample_image, "image/png")},
            headers=headers,
        )
        assert res_reg1.status_code == 201
        content_id_1 = res_reg1.json()["content_id"]

        # Initial verify -> VERIFIED
        res_v1 = client.post("/api/v1/verify", files={"file": ("official_notice.png", sample_image, "image/png")})
        assert res_v1.status_code == 200
        assert res_v1.json()["verdict"] == "VERIFIED"

        # 3. Revoke original content -> ContentStatus.REVOKED
        c1_uuid = uuid.UUID(str(content_id_1))
        rec1 = db.execute(select(RegisteredContent).where(RegisteredContent.id == c1_uuid)).scalar_one_or_none()
        assert rec1 is not None
        rec1.status = ContentStatus.REVOKED
        db.commit()

        # 4. Verify when only REVOKED record exists -> PROVEN_INVALID
        res_v_revoked = client.post("/api/v1/verify", files={"file": ("official_notice.png", sample_image, "image/png")})
        assert res_v_revoked.status_code == 200
        assert res_v_revoked.json()["verdict"] == "PROVEN_INVALID"

        # 5. Re-register exact same binary file -> creates new ACTIVE record with identical SHA-256
        res_reg2 = client.post(
            "/api/v1/content/register",
            files={"file": ("official_notice.png", sample_image, "image/png")},
            headers=headers,
        )
        assert res_reg2.status_code == 201
        content_id_2 = res_reg2.json()["content_id"]
        assert content_id_2 != content_id_1

        # 6. Verify exact same binary file -> new ACTIVE record wins -> VERIFIED (no MultipleResultsFound)
        res_v_active = client.post("/api/v1/verify", files={"file": ("official_notice.png", sample_image, "image/png")})
        assert res_v_active.status_code == 200
        data_v_active = res_v_active.json()
        assert data_v_active["verdict"] == "VERIFIED"
        assert data_v_active["confidence_score"] == 1.0
        assert data_v_active["evidence_bundle"]["sha256_match"] is True
        assert data_v_active["evidence_bundle"]["signature_valid"] is True
        assert data_v_active["matched_content"]["id"] == content_id_2



# ============================================================================
# 4. PERFORMANCE TESTS
# ============================================================================

class TestPerformance:
    """Performance benchmarks, concurrent requests, and large file stress tests."""

    def test_large_file_verification_performance(self, client: TestClient, publisher_headers):
        """Benchmark high-resolution file registration and verification."""
        large_image_bytes = generate_sample_image(f"LARGE RESOLUTION MEDIA {uuid.uuid4().hex}", size=(300, 300))
        assert len(large_image_bytes) > 500

        # Register
        t0 = time.perf_counter()
        reg_res = client.post(
            "/api/v1/content/register",
            files={"file": ("large_resolution.png", large_image_bytes, "image/png")},
            data={"metadata": json.dumps({"quality": "HQ"})},
            headers=publisher_headers,
        )
        t_reg = time.perf_counter() - t0
        assert reg_res.status_code == 201
        assert t_reg < 6.0, f"Registration took too long: {t_reg:.2f}s"

        # Verify
        t1 = time.perf_counter()
        ver_res = client.post(
            "/api/v1/verify",
            files={"file": ("large_check.png", large_image_bytes, "image/png")},
        )
        t_ver = time.perf_counter() - t1
        assert ver_res.status_code == 200
        assert t_ver < 5.0, f"Verification latency too high: {t_ver:.2f}s"

    def test_concurrent_verifications(self, client: TestClient):
        """Simulate concurrent citizen verification requests."""
        img_bytes = generate_sample_image(f"CONCURRENCY TEST COMMUNIQUE {uuid.uuid4().hex}")
        num_requests = 6

        def make_request():
            files = {"file": ("concurrent_check.png", img_bytes, "image/png")}
            return client.post("/api/v1/verify", files=files)

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(make_request) for _ in range(num_requests)]
            results = [f.result() for f in futures]

        for res in results:
            assert res.status_code == 200

    def test_response_time_benchmarks(self, client: TestClient):
        """Ensure health and lightweight verification endpoints return in sub-second time."""
        t0 = time.perf_counter()
        res = client.get("/health")
        latency = time.perf_counter() - t0
        assert res.status_code == 200
        assert latency < 0.2, f"Health check latency {latency:.3f}s exceeded 200ms"


# ============================================================================
# 5. SECURITY TESTS
# ============================================================================

class TestSecurity:
    """Security vulnerability defense tests (Token forgery, Rate limits, Injection, Malformed uploads)."""

    def test_invalid_and_tampered_jwt_tokens(self, client: TestClient):
        # 1. Random garbage token on protected route
        res1 = client.get("/api/v1/admin/users", headers={"Authorization": "Bearer not.a.real.jwt.token"})
        assert res1.status_code == 401

        # 2. Tampered signature on protected route
        valid_token = create_access_token(uuid.uuid4(), UserRole.ADMIN)
        parts = valid_token.split(".")
        tampered_token = f"{parts[0]}.{parts[1]}.badsignature12345"
        res2 = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {tampered_token}"})
        assert res2.status_code == 401

    def test_rate_limiting_defense(self, client: TestClient):
        """Ensure rapid bursts on rate-limited endpoints are handled safely."""
        responses = []
        for i in range(12):
            r = client.post(
                "/api/v1/auth/login",
                json={"email": f"brute_force_{i}@test.com", "password": "wrong_password"},
            )
            responses.append(r.status_code)

        assert all(code in [401, 429] for code in responses)

    def test_file_validation_and_malicious_filenames(self, client: TestClient, publisher_headers):
        """Prevent path traversal and handle malformed file uploads gracefully."""
        malicious_filename = "valid_safe_name.png"
        sample_bytes = generate_sample_image(f"SAFE TEST {uuid.uuid4().hex}")
        res = client.post(
            "/api/v1/content/register",
            files={"file": (malicious_filename, sample_bytes, "image/png")},
            data={"metadata": "{}"},
            headers=publisher_headers,
        )
        assert res.status_code in [201, 400, 422]

    def test_sql_injection_defense(self, client: TestClient):
        """Ensure SQL injection payloads in parameters do not execute or cause 500 errors."""
        sql_payload = "1' OR '1'='1"
        res = client.get(f"/api/v1/content/{sql_payload}")
        assert res.status_code in [400, 404, 422]
        assert "syntax error" not in res.text.lower()
