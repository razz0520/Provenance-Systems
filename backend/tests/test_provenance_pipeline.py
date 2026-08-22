"""End-to-End Test for the Complete 4-Mechanism Provenance Verification Pipeline."""

import io
from PIL import Image, ImageDraw
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _create_sample_image(text: str = "OFFICIAL GOV PRESS RELEASE") -> bytes:
    """Create a real PIL image representing an official government announcement."""
    img = Image.new("RGB", (300, 300), color=(240, 245, 250))
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 280, 280], outline=(30, 58, 95), width=4)
    draw.text((40, 140), text, fill=(15, 23, 42))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def _create_compressed_image(original_bytes: bytes) -> bytes:
    """Create a slightly re-encoded JPEG version to test near-duplicate perceptual similarity."""
    img = Image.open(io.BytesIO(original_bytes))
    buffer = io.BytesIO()
    img.convert("RGB").save(buffer, format="JPEG", quality=80)
    return buffer.getvalue()


def _create_distinct_image() -> bytes:
    """Create a completely distinct image (vibrant red with circles) for negative testing."""
    img = Image.new("RGB", (300, 300), color=(180, 20, 20))
    draw = ImageDraw.Draw(img)
    draw.ellipse([40, 40, 260, 260], fill=(255, 220, 0), outline=(0, 0, 0), width=6)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


class TestProvenancePipelineE2E:
    """Validate all 4 security mechanisms + hash chain ledger end-to-end."""

    def test_complete_provenance_pipeline(self, client: TestClient):
        # 1. Register Publisher
        reg_payload = {
            "email": "ministry.press@gov.in",
            "password": "Password123!",
            "organization_name": "Ministry of Information & Broadcasting",
            "organization_domain": "gov.in",
            "department": "Press Information Bureau",
            "designation": "Director of Communications",
        }
        reg_res = client.post("/api/v1/auth/register", json=reg_payload)
        assert reg_res.status_code == 201

        # 2. Login Publisher
        login_res = client.post(
            "/api/v1/auth/login",
            json={"email": "ministry.press@gov.in", "password": "Password123!"},
        )
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 3. Upload & Register Official Image
        image_bytes = _create_sample_image("NATIONAL ECONOMIC COMMUNIQUE 2026")
        files = {"file": ("official_communique.png", image_bytes, "image/png")}
        data = {"metadata": '{"category": "PRESS_RELEASE", "urgency": "HIGH"}'}

        register_res = client.post(
            "/api/v1/content/register",
            files=files,
            data=data,
            headers=headers,
        )
        assert register_res.status_code == 201
        reg_data = register_res.json()

        # Check Mechanism 1 (SHA-256), Mechanism 2 (Signature), Mechanism 5 (Ledger) in Registration Response
        assert len(reg_data["sha256_hash"]) == 64
        assert len(reg_data["manifest_signature"]) > 20
        assert reg_data["hash_chain_block_id"] >= 1
        content_id = reg_data["content_id"]

        # Inspect Content Record & Mechanism 4 (Perceptual Hash)
        detail_res = client.get(f"/api/v1/content/{content_id}")
        assert detail_res.status_code == 200
        content_detail = detail_res.json()
        phash_data = content_detail["perceptual_hash"]
        assert "phash" in phash_data
        assert "dhash" in phash_data
        assert len(phash_data["phash"]) == 16  # 64-bit hexadecimal pHash

        # 4. Exact Verification via /api/v1/verify
        verify_files = {"file": ("citizen_upload.png", image_bytes, "image/png")}
        verify_res = client.post("/api/v1/verify", files=verify_files)
        assert verify_res.status_code == 200
        verify_data = verify_res.json()

        assert verify_data["verdict"] == "VERIFIED"
        assert verify_data["confidence_score"] == 1.0

        evidence = verify_data["evidence_bundle"]
        # Mechanism 1: SHA-256
        assert evidence["sha256_match"] is True
        assert evidence["sha256_submitted"] == reg_data["sha256_hash"]
        assert evidence["matched_hash"] == reg_data["sha256_hash"]

        # Mechanism 2: Digital Signature (Ed25519)
        assert evidence["signature_valid"] is True
        assert len(evidence["digital_signature"]) > 20
        assert evidence["publisher_name"] == "Ministry of Information & Broadcasting"
        assert evidence["publisher_domain"] == "gov.in"

        # Mechanism 3: Manifest
        assert evidence["manifest_valid"] is True
        assert evidence["manifest_data"] is not None
        assert evidence["manifest_data"]["content_hash"] == reg_data["sha256_hash"]

        # Mechanism 4: Perceptual Fingerprint
        assert evidence["perceptual_match_status"] == "EXACT_MATCH"
        assert evidence["perceptual_similarity_score"] == 100.0
        assert "phash" in evidence["perceptual_hash_submitted"]
        assert "phash" in evidence["perceptual_hash_matched"]

        # Mechanism 5: Ledger Anchor
        assert evidence["chain_integrity"] is True
        assert evidence["chain_block_id"] == reg_data["hash_chain_block_id"]

        # 5. Fuzzy Perceptual Match (JPEG Compressed Version)
        compressed_bytes = _create_compressed_image(image_bytes)
        comp_files = {"file": ("forwarded_on_social_media.jpg", compressed_bytes, "image/jpeg")}
        comp_res = client.post("/api/v1/verify", files=comp_files)
        assert comp_res.status_code == 200
        comp_data = comp_res.json()

        assert comp_data["verdict"] == "VERIFIED"
        comp_evidence = comp_data["evidence_bundle"]
        assert comp_evidence["sha256_match"] is False  # SHA-256 differs due to JPEG re-compression
        assert comp_evidence["match_type"] == "PERCEPTUAL_SIMILARITY"
        assert comp_evidence["perceptual_similarity_score"] >= 90.0  # High perceptual similarity
        assert comp_evidence["signature_valid"] is True

        # 6. Unregistered Distinct Image Verification
        distinct_bytes = _create_distinct_image()
        unreg_files = {"file": ("distinct_image.png", distinct_bytes, "image/png")}
        unreg_res = client.post("/api/v1/verify", files=unreg_files)
        assert unreg_res.status_code == 200
        unreg_data = unreg_res.json()

        assert unreg_data["verdict"] == "UNSIGNED"
        assert unreg_data["confidence_score"] == 0.0
        unreg_ev = unreg_data["evidence_bundle"]
        assert unreg_ev["match_type"] == "NONE"
        assert unreg_ev["sha256_match"] is False
        assert unreg_ev["signature_valid"] is False
        assert unreg_ev["manifest_valid"] is False
        assert unreg_ev["matched_hash"] is None
