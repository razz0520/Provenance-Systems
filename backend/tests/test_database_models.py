import datetime
import uuid
import pytest
from sqlalchemy import select, text
from app.database import engine, SessionLocal, init_db, drop_db
from app.models import (
    Base,
    User,
    Credential,
    RegisteredContent,
    CryptographicManifest,
    HashChainEntry,
    AuditLog,
    VerificationAttempt,
    DomainWhitelist,
    UserRole,
    CredentialType,
    CredentialStatus,
    ContentType,
    ContentStatus,
    VerificationVerdict,
)


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Ensure clean tables before test session and clean up after."""
    drop_db()
    init_db()
    yield
    drop_db()
    init_db()


@pytest.fixture
def db():
    """Provide a database session for each test and cleanly remove data afterwards."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        # Clean all table records between tests
        with engine.connect() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(text(f'TRUNCATE TABLE "{table.name}" CASCADE'))
            conn.commit()


def test_user_creation_and_dict(db):
    """Test User creation, attributes, __repr__, and to_dict method."""
    user = User(
        email="publisher@gov.in",
        password_hash="hashed_pw_123",
        role=UserRole.PUBLISHER,
        organization_name="Ministry of Information",
        organization_domain="gov.in",
        department="Media Relations",
        designation="Chief Registrar",
        public_key="ed25519_pk_abcdef123456",
        is_active=True,
        is_verified=True,
        mfa_enabled=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    assert user.id is not None
    assert user.role == UserRole.PUBLISHER
    assert "publisher@gov.in" in repr(user)

    # Test to_dict without sensitive fields
    user_dict = user.to_dict()
    assert user_dict["email"] == "publisher@gov.in"
    assert user_dict["role"] == "PUBLISHER"
    assert "password_hash" not in user_dict
    assert "mfa_secret" not in user_dict

    # Test to_dict with sensitive fields
    sensitive_dict = user.to_dict(include_sensitive=True)
    assert sensitive_dict["password_hash"] == "hashed_pw_123"


def test_credential_model(db):
    """Test Credential creation, relation to User, and methods."""
    user = User(
        email="cred_user@gov.in",
        role=UserRole.PUBLISHER,
        organization_name="Gov Dept",
        organization_domain="gov.in",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    now = datetime.datetime.now(datetime.timezone.utc)
    one_year_later = now + datetime.timedelta(days=365)

    cred = Credential(
        publisher_id=user.id,
        credential_type=CredentialType.PRIMARY,
        status=CredentialStatus.ACTIVE,
        valid_from=now,
        valid_until=one_year_later,
    )
    db.add(cred)
    db.commit()
    db.refresh(cred)

    assert cred.id is not None
    assert cred.publisher.email == "cred_user@gov.in"
    assert len(user.credentials) == 1
    assert "PRIMARY" in repr(cred)

    cred_dict = cred.to_dict()
    assert cred_dict["credential_type"] == "PRIMARY"
    assert cred_dict["status"] == "ACTIVE"


def test_registered_content_and_relationships(db):
    """Test RegisteredContent, Manifest, HashChain, and cascade deletion."""
    user = User(
        email="content_author@gov.in",
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

    content = RegisteredContent(
        publisher_id=user.id,
        credential_id=cred.id,
        content_type=ContentType.VIDEO,
        original_filename="press_release.mp4",
        stored_filename="stored_abc123.mp4",
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        perceptual_hash={"phash": "01010101", "dhash": "10101010"},
        watermark_data={"watermark_id": "wm-999"},
        file_size=1048576,
        mime_type="video/mp4",
        duration_seconds=120.5,
        status=ContentStatus.ACTIVE,
    )
    db.add(content)
    db.commit()
    db.refresh(content)

    # Add CryptographicManifest
    manifest = CryptographicManifest(
        content_id=content.id,
        manifest_data={"version": "1.0", "hash": content.sha256_hash},
        digital_signature="sig_ed25519_test_signature",
        signing_algorithm="Ed25519",
    )
    db.add(manifest)

    # Add HashChainEntry
    hash_chain = HashChainEntry(
        content_id=content.id,
        prev_hash="0000000000000000000000000000000000000000000000000000000000000000",
        current_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        timestamp=now,
    )
    db.add(hash_chain)
    db.commit()
    db.refresh(content)

    assert content.manifest is not None
    assert content.manifest.signing_algorithm == "Ed25519"
    assert content.hash_chain_entry is not None
    assert content.hash_chain_entry.id is not None

    content_dict = content.to_dict()
    assert content_dict["content_type"] == "VIDEO"
    assert content_dict["file_size"] == 1048576
    assert content_dict["duration_seconds"] == 120.5

    manifest_dict = content.manifest.to_dict()
    assert manifest_dict["signing_algorithm"] == "Ed25519"

    hash_dict = content.hash_chain_entry.to_dict()
    assert hash_dict["current_hash"] == content.sha256_hash

    # Test cascade delete: Deleting content deletes manifest and hash chain entry
    content_id = content.id
    db.delete(content)
    db.commit()

    deleted_manifest = db.execute(
        select(CryptographicManifest).where(CryptographicManifest.content_id == content_id)
    ).scalar_one_or_none()
    deleted_chain = db.execute(
        select(HashChainEntry).where(HashChainEntry.content_id == content_id)
    ).scalar_one_or_none()

    assert deleted_manifest is None
    assert deleted_chain is None


def test_superseded_content_self_reference(db):
    """Test self-referencing superseded_by relationship on RegisteredContent."""
    user = User(
        email="editor@gov.in",
        role=UserRole.PUBLISHER,
        organization_name="Gov Dept",
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

    # New version
    v2_content = RegisteredContent(
        publisher_id=user.id,
        credential_id=cred.id,
        content_type=ContentType.PDF,
        original_filename="report_v2.pdf",
        stored_filename="stored_v2.pdf",
        sha256_hash="2222222222222222222222222222222222222222222222222222222222222222",
        perceptual_hash={},
        file_size=50000,
        mime_type="application/pdf",
        status=ContentStatus.ACTIVE,
    )
    db.add(v2_content)
    db.commit()
    db.refresh(v2_content)

    # Old version superseded by v2
    v1_content = RegisteredContent(
        publisher_id=user.id,
        credential_id=cred.id,
        content_type=ContentType.PDF,
        original_filename="report_v1.pdf",
        stored_filename="stored_v1.pdf",
        sha256_hash="1111111111111111111111111111111111111111111111111111111111111111",
        perceptual_hash={},
        file_size=45000,
        mime_type="application/pdf",
        status=ContentStatus.SUPERSEDED,
        superseded_by_id=v2_content.id,
    )
    db.add(v1_content)
    db.commit()
    db.refresh(v1_content)

    assert v1_content.superseded_by is not None
    assert v1_content.superseded_by.id == v2_content.id


def test_audit_log_and_verification_attempt(db):
    """Test AuditLog, VerificationAttempt, and DomainWhitelist models."""
    user = User(
        email="admin_audit@gov.in",
        role=UserRole.ADMIN,
        organization_name="Security Operations",
        organization_domain="gov.in",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # AuditLog
    log = AuditLog(
        actor_id=user.id,
        action="CONTENT_VERIFY",
        details={"ip": "127.0.0.1", "status": "SUCCESS"},
        ip_address="127.0.0.1",
        user_agent="Mozilla/5.0",
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    assert log.id is not None
    assert log.actor.email == "admin_audit@gov.in"
    assert log.to_dict()["action"] == "CONTENT_VERIFY"

    # VerificationAttempt
    attempt = VerificationAttempt(
        submitted_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        verdict=VerificationVerdict.VERIFIED,
        evidence_bundle={"match": "exact", "signature_valid": True},
        confidence_score=0.99,
        verification_time_ms=45,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    assert attempt.id is not None
    assert attempt.verdict == VerificationVerdict.VERIFIED
    assert attempt.confidence_score == 0.99
    assert attempt.to_dict()["verdict"] == "VERIFIED"

    # DomainWhitelist
    whitelist = DomainWhitelist(
        domain="pib.gov.in",
        allowed_roles=["PUBLISHER", "ADMIN"],
        is_active=True,
    )
    db.add(whitelist)
    db.commit()
    db.refresh(whitelist)

    assert whitelist.id is not None
    assert whitelist.domain == "pib.gov.in"
    assert "PUBLISHER" in whitelist.allowed_roles
    assert whitelist.to_dict()["domain"] == "pib.gov.in"
