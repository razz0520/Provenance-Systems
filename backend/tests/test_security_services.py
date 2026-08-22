import datetime
import io
import os
import tempfile
import uuid
import numpy as np
from PIL import Image
import pytest
import soundfile as sf
import cv2

from app.database import engine, SessionLocal, init_db, drop_db
from app.models import (
    Base,
    User,
    UserRole,
    Credential,
    CredentialType,
    CredentialStatus,
    RegisteredContent,
    ContentType,
    ContentStatus,
    HashChainEntry,
)
from app.core import (
    calculate_file_hash,
    calculate_bytes_hash,
    verify_file_hash,
    generate_image_phash,
    generate_image_dhash,
    generate_video_phash,
    generate_audio_fingerprint,
    compare_perceptual_hashes,
    create_genesis_block,
    add_block,
    verify_chain,
    get_chain_state,
    detect_tampering,
    generate_ed25519_keypair,
    serialize_private_key,
    serialize_public_key,
    deserialize_private_key,
    deserialize_public_key,
    serialize_keys,
    deserialize_keys,
    store_keypair,
    get_public_key,
    sign_data,
    verify_data_signature,
    sign_manifest,
    verify_signature,
    create_manifest,
    serialize_manifest,
    deserialize_manifest,
    validate_manifest,
)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


# ============================================================================
# 1. SHA256 Tests
# ============================================================================

def test_sha256_file_and_bytes():
    payload = b"Deepfake Resistant Provenance Protocol 2026"
    expected = "97193d5500d41e7dc6d0a7a0b58e7279fb04bbbe2d02cbe3e9ee7c3558ffb4fb"

    # Bytes hash
    h_bytes = calculate_bytes_hash(payload)
    assert len(h_bytes) == 64

    # File hash
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(payload)
        temp_name = f.name

    try:
        f_hash = calculate_file_hash(temp_name)
        assert f_hash == h_bytes
        assert verify_file_hash(temp_name, f_hash) is True
        assert verify_file_hash(temp_name, "0000000000000000000000000000000000000000000000000000000000000000") is False
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


# ============================================================================
# 2. Perceptual Hashing Tests
# ============================================================================

def test_image_perceptual_hashes():
    # Create synthetic image 1
    img1 = Image.new("RGB", (100, 100), color=(73, 109, 137))
    phash1 = generate_image_phash(img1)
    dhash1 = generate_image_dhash(img1)

    assert len(phash1) > 0
    assert len(dhash1) > 0

    # Same image gives 100% similarity
    assert compare_perceptual_hashes(phash1, phash1) == 100.0

    # Slightly modified image
    img2 = Image.new("RGB", (100, 100), color=(75, 110, 140))
    phash2 = generate_image_phash(img2)
    score = compare_perceptual_hashes(phash1, phash2)
    assert score >= 90.0

    # Completely different image (checkerboard/noise)
    arr = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    img_diff = Image.fromarray(arr)
    phash_diff = generate_image_phash(img_diff)
    diff_score = compare_perceptual_hashes(phash1, phash_diff)
    assert diff_score < 90.0


def test_video_perceptual_hashing():
    # Create temporary video
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        temp_video = f.name

    try:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(temp_video, fourcc, 10.0, (64, 64))
        for i in range(20):
            frame = np.full((64, 64, 3), fill_value=(i * 10, 50, 100), dtype=np.uint8)
            out.write(frame)
        out.release()

        v_result = generate_video_phash(temp_video, fps=1.0)
        assert v_result["total_video_frames"] == 20
        assert v_result["sampled_count"] > 0
        assert len(v_result["composite_phash"]) == 64
        assert len(v_result["frame_hashes"]) > 0

        # Self comparison gives 100%
        assert compare_perceptual_hashes(v_result, v_result) == 100.0
    finally:
        if os.path.exists(temp_video):
            os.unlink(temp_video)


def test_audio_fingerprinting():
    # Create temporary sine wave audio file
    sr = 22050
    duration = 0.5
    t = np.linspace(0, duration, int(sr * duration), False)
    sine_wave = 0.5 * np.sin(2 * np.pi * 440 * t)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        temp_audio = f.name

    try:
        sf.write(temp_audio, sine_wave, sr)
        fp = generate_audio_fingerprint(temp_audio)
        assert len(fp) == 64

        # From bytes
        with open(temp_audio, "rb") as af:
            audio_bytes = af.read()
        fp_bytes = generate_audio_fingerprint(audio_bytes)
        assert len(fp_bytes) == 64
    finally:
        if os.path.exists(temp_audio):
            os.unlink(temp_audio)


# ============================================================================
# 3. Hash Chain Integrity Tests
# ============================================================================

def test_hash_chain_workflow_and_tampering(db):
    user = User(
        email=f"chain_user_{uuid.uuid4().hex[:6]}@gov.in",
        role=UserRole.PUBLISHER,
        organization_name="Press Bureau",
        organization_domain="gov.in",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    now = datetime.datetime.now(datetime.timezone.utc)
    cred = Credential(
        publisher_id=user.id,
        credential_type=CredentialType.PRIMARY,
        status=CredentialStatus.ACTIVE,
        valid_from=now,
        valid_until=now + datetime.timedelta(days=30),
    )
    db.add(cred)
    db.commit()
    db.refresh(cred)

    contents = []
    for i in range(3):
        c = RegisteredContent(
            publisher_id=user.id,
            credential_id=cred.id,
            content_type=ContentType.PDF,
            original_filename=f"doc_{i}.pdf",
            stored_filename=f"stored_{i}.pdf",
            sha256_hash=f"{i}" * 64,
            perceptual_hash={},
            file_size=1000 * (i + 1),
            mime_type="application/pdf",
            status=ContentStatus.ACTIVE,
        )
        db.add(c)
        contents.append(c)
    db.commit()
    for c in contents:
        db.refresh(c)

    # Add blocks
    b1 = add_block(db, contents[0].id, {"file": "doc1.pdf"})
    assert b1.prev_hash == create_genesis_block()

    b2 = add_block(db, contents[1].id, {"file": "doc2.pdf"})
    assert b2.prev_hash == b1.current_hash

    b3 = add_block(db, contents[2].id, {"file": "doc3.pdf"})
    assert b3.prev_hash == b2.current_hash

    # Verify chain
    is_valid, broken_idx = verify_chain(db)
    assert is_valid is True
    assert broken_idx is None
    assert detect_tampering(db) is False

    state = get_chain_state(db)
    assert state["is_valid"] is True
    assert state["total_blocks"] >= 3

    # Tamper with block 2
    b2.current_hash = "f" * 64
    db.commit()

    is_valid, broken_idx = verify_chain(db)
    assert is_valid is False
    assert broken_idx == b3.id
    assert detect_tampering(db) is True


# ============================================================================
# 4. Digital Signatures & Key Management
# ============================================================================

def test_ed25519_key_management_and_signatures(db):
    # Generate keypair
    private_key, public_key = generate_ed25519_keypair()

    # Serialization
    priv_pem, pub_pem = serialize_keys(private_key, public_key)
    assert "BEGIN PRIVATE KEY" in priv_pem
    assert "BEGIN PUBLIC KEY" in pub_pem

    # Deserialization
    loaded_priv, loaded_pub = deserialize_keys(priv_pem, pub_pem)

    # Sign data
    msg = "Official Government Gazette Notification #2026-08"
    signature = sign_data(msg, loaded_priv)
    assert len(signature) > 0

    # Verify data signature
    assert verify_data_signature(msg, signature, loaded_pub) is True
    assert verify_data_signature("Tampered text", signature, loaded_pub) is False

    # Store in User model
    user = User(
        email=f"signer_{uuid.uuid4().hex[:6]}@gov.in",
        role=UserRole.PUBLISHER,
        organization_name="Press Council",
        organization_domain="gov.in",
    )
    db.add(user)
    db.commit()

    assert store_keypair(db, user.id, pub_pem) is True
    retrieved_pub = get_public_key(db, user.id)
    assert retrieved_pub == pub_pem


# ============================================================================
# 5. Manifest Creation, Serialization, and Verification
# ============================================================================

def test_manifest_lifecycle():
    pub_id = str(uuid.uuid4())
    content_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    manifest = create_manifest(
        publisher_id=pub_id,
        content_hash=content_hash,
        content_type="VIDEO",
        metadata={"title": "Official Announcement"},
    )

    assert validate_manifest(manifest) is True

    # Deterministic serialization
    canonical_bytes1 = serialize_manifest(manifest)
    canonical_bytes2 = serialize_manifest(manifest)
    assert canonical_bytes1 == canonical_bytes2

    # Deserialization
    parsed = deserialize_manifest(canonical_bytes1)
    assert parsed["content_hash"] == content_hash

    # Signing manifest
    priv_key, pub_key = generate_ed25519_keypair()
    sig = sign_manifest(manifest, priv_key)

    # Verify signature
    assert verify_signature(manifest, sig, pub_key) is True

    # Mutate manifest -> should fail signature verification
    tampered_manifest = dict(manifest)
    tampered_manifest["content_type"] = "AUDIO"
    assert verify_signature(tampered_manifest, sig, pub_key) is False
