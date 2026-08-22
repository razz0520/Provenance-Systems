import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


# ============================================================================
# Base Declarative Class
# ============================================================================

class Base(DeclarativeBase):
    """SQLAlchemy 2.0 Base Declarative Class"""
    pass


# ============================================================================
# Enumerations
# ============================================================================

class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    PUBLISHER = "PUBLISHER"
    VIEWER = "VIEWER"


class CredentialType(str, enum.Enum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"


class CredentialStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class ContentType(str, enum.Enum):
    VIDEO = "VIDEO"
    IMAGE = "IMAGE"
    AUDIO = "AUDIO"
    PDF = "PDF"
    TEXT = "TEXT"


class ContentStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    REVOKED = "REVOKED"


class VerificationVerdict(str, enum.Enum):
    VERIFIED = "VERIFIED"
    SUSPICIOUS = "SUSPICIOUS"
    UNSIGNED = "UNSIGNED"
    PROVEN_INVALID = "PROVEN_INVALID"


# ============================================================================
# Helper Functions
# ============================================================================

def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


def _serialize_val(val: Any) -> Any:
    """Serialize values for to_dict() output."""
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, enum.Enum):
        return val.value
    return val


# ============================================================================
# 1. User Model
# ============================================================================

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    password_hash: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    google_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
        index=True,
    )
    google_email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(
            UserRole,
            name="user_role_enum",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=UserRole.VIEWER,
    )
    organization_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    organization_domain: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    department: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    designation: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    public_key: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Ed25519 public key (PEM/Hex encoded)",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    mfa_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    mfa_secret: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_login_ip: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
    )
    login_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    # Relationships
    credentials: Mapped[List["Credential"]] = relationship(
        "Credential",
        back_populates="publisher",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    registered_contents: Mapped[List["RegisteredContent"]] = relationship(
        "RegisteredContent",
        back_populates="publisher",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog",
        back_populates="actor",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("idx_users_org_domain_role", "organization_domain", "role"),
    )

    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """Convert User model to dictionary."""
        data = {
            "id": str(self.id) if self.id else None,
            "email": self.email,
            "google_id": self.google_id,
            "google_email": self.google_email,
            "role": self.role.value if isinstance(self.role, enum.Enum) else self.role,
            "organization_name": self.organization_name,
            "organization_domain": self.organization_domain,
            "department": self.department,
            "designation": self.designation,
            "public_key": self.public_key,
            "is_active": self.is_active,
            "is_verified": self.is_verified,
            "mfa_enabled": self.mfa_enabled,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
            "last_login_ip": self.last_login_ip,
            "login_count": self.login_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_sensitive:
            data["password_hash"] = self.password_hash
            data["mfa_secret"] = self.mfa_secret
        return data

    def __repr__(self) -> str:
        return (
            f"<User(id={self.id}, email='{self.email}', "
            f"role='{self.role.value if isinstance(self.role, enum.Enum) else self.role}', "
            f"organization='{self.organization_name}', is_active={self.is_active})>"
        )


# ============================================================================
# 2. Credential Model
# ============================================================================

class Credential(Base):
    __tablename__ = "credentials"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    publisher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    credential_type: Mapped[CredentialType] = mapped_column(
        SQLEnum(
            CredentialType,
            name="credential_type_enum",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=CredentialType.PRIMARY,
    )
    status: Mapped[CredentialStatus] = mapped_column(
        SQLEnum(
            CredentialStatus,
            name="credential_status_enum",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=CredentialStatus.ACTIVE,
        index=True,
    )
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    valid_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revocation_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utc_now,
        nullable=False,
    )

    # Relationships
    publisher: Mapped["User"] = relationship(
        "User",
        back_populates="credentials",
    )
    registered_contents: Mapped[List["RegisteredContent"]] = relationship(
        "RegisteredContent",
        back_populates="credential",
        passive_deletes="all",
    )

    __table_args__ = (
        Index("idx_credentials_publisher_status", "publisher_id", "status"),
        Index("idx_credentials_validity", "valid_from", "valid_until"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert Credential model to dictionary."""
        return {
            "id": str(self.id) if self.id else None,
            "publisher_id": str(self.publisher_id) if self.publisher_id else None,
            "credential_type": self.credential_type.value if isinstance(self.credential_type, enum.Enum) else self.credential_type,
            "status": self.status.value if isinstance(self.status, enum.Enum) else self.status,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "revocation_reason": self.revocation_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<Credential(id={self.id}, publisher_id={self.publisher_id}, "
            f"type='{self.credential_type.value if isinstance(self.credential_type, enum.Enum) else self.credential_type}', "
            f"status='{self.status.value if isinstance(self.status, enum.Enum) else self.status}')>"
        )


# ============================================================================
# 3. RegisteredContent Model
# ============================================================================

class RegisteredContent(Base):
    __tablename__ = "registered_contents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    publisher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    credential_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("credentials.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    content_type: Mapped[ContentType] = mapped_column(
        SQLEnum(
            ContentType,
            name="content_type_enum",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    stored_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    sha256_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    perceptual_hash: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )
    watermark_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    file_size: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    mime_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    duration_seconds: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    status: Mapped[ContentStatus] = mapped_column(
        SQLEnum(
            ContentStatus,
            name="content_status_enum",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=ContentStatus.ACTIVE,
        index=True,
    )
    superseded_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_contents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utc_now,
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    # Relationships
    publisher: Mapped["User"] = relationship(
        "User",
        back_populates="registered_contents",
    )
    credential: Mapped["Credential"] = relationship(
        "Credential",
        back_populates="registered_contents",
    )
    superseded_by: Mapped[Optional["RegisteredContent"]] = relationship(
        "RegisteredContent",
        remote_side=[id],
        backref="superseded_contents",
        foreign_keys=[superseded_by_id],
    )
    manifest: Mapped[Optional["CryptographicManifest"]] = relationship(
        "CryptographicManifest",
        back_populates="content",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    hash_chain_entry: Mapped[Optional["HashChainEntry"]] = relationship(
        "HashChainEntry",
        back_populates="content",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    verification_attempts: Mapped[List["VerificationAttempt"]] = relationship(
        "VerificationAttempt",
        back_populates="matched_content",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("idx_registered_content_sha256", "sha256_hash"),
        Index("idx_registered_content_status_type", "status", "content_type"),
        Index("idx_registered_content_pub_status", "publisher_id", "status"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert RegisteredContent model to dictionary."""
        return {
            "id": str(self.id) if self.id else None,
            "publisher_id": str(self.publisher_id) if self.publisher_id else None,
            "credential_id": str(self.credential_id) if self.credential_id else None,
            "content_type": self.content_type.value if isinstance(self.content_type, enum.Enum) else self.content_type,
            "original_filename": self.original_filename,
            "stored_filename": self.stored_filename,
            "sha256_hash": self.sha256_hash,
            "perceptual_hash": self.perceptual_hash,
            "watermark_data": self.watermark_data,
            "file_size": self.file_size,
            "mime_type": self.mime_type,
            "duration_seconds": self.duration_seconds,
            "status": self.status.value if isinstance(self.status, enum.Enum) else self.status,
            "superseded_by_id": str(self.superseded_by_id) if self.superseded_by_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<RegisteredContent(id={self.id}, "
            f"type='{self.content_type.value if isinstance(self.content_type, enum.Enum) else self.content_type}', "
            f"filename='{self.original_filename}', sha256='{self.sha256_hash[:8]}...', "
            f"status='{self.status.value if isinstance(self.status, enum.Enum) else self.status}')>"
        )


# ============================================================================
# 4. CryptographicManifest Model
# ============================================================================

class CryptographicManifest(Base):
    __tablename__ = "cryptographic_manifests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    content_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_contents.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    manifest_data: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )
    digital_signature: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    signing_algorithm: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="Ed25519",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utc_now,
        nullable=False,
    )

    # Relationships
    content: Mapped["RegisteredContent"] = relationship(
        "RegisteredContent",
        back_populates="manifest",
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert CryptographicManifest model to dictionary."""
        return {
            "id": str(self.id) if self.id else None,
            "content_id": str(self.content_id) if self.content_id else None,
            "manifest_data": self.manifest_data,
            "digital_signature": self.digital_signature,
            "signing_algorithm": self.signing_algorithm,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<CryptographicManifest(id={self.id}, content_id={self.content_id}, "
            f"algorithm='{self.signing_algorithm}')>"
        )


# ============================================================================
# 5. HashChainEntry Model
# ============================================================================

class HashChainEntry(Base):
    __tablename__ = "hash_chain_entries"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    content_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_contents.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    prev_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    current_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utc_now,
        nullable=False,
    )

    # Relationships
    content: Mapped["RegisteredContent"] = relationship(
        "RegisteredContent",
        back_populates="hash_chain_entry",
    )

    __table_args__ = (
        Index("idx_hash_chain_prev_current", "prev_hash", "current_hash"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert HashChainEntry model to dictionary."""
        return {
            "id": self.id,
            "content_id": str(self.content_id) if self.content_id else None,
            "prev_hash": self.prev_hash,
            "current_hash": self.current_hash,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<HashChainEntry(id={self.id}, content_id={self.content_id}, "
            f"prev_hash='{self.prev_hash[:8]}...', current_hash='{self.current_hash[:8]}...')>"
        )


# ============================================================================
# 6. AuditLog Model
# ============================================================================

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    details: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utc_now,
        nullable=False,
        index=True,
    )

    # Relationships
    actor: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="audit_logs",
    )

    __table_args__ = (
        Index("idx_audit_logs_actor_action", "actor_id", "action"),
        Index("idx_audit_logs_created_at", "created_at"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert AuditLog model to dictionary."""
        return {
            "id": str(self.id) if self.id else None,
            "actor_id": str(self.actor_id) if self.actor_id else None,
            "action": self.action,
            "details": self.details,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<AuditLog(id={self.id}, actor_id={self.actor_id}, "
            f"action='{self.action}', created_at='{self.created_at}')>"
        )


# ============================================================================
# 7. VerificationAttempt Model
# ============================================================================

class VerificationAttempt(Base):
    __tablename__ = "verification_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    submitted_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    matched_content_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_contents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    verdict: Mapped[VerificationVerdict] = mapped_column(
        SQLEnum(
            VerificationVerdict,
            name="verification_verdict_enum",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        index=True,
    )
    evidence_bundle: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    confidence_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    verification_time_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utc_now,
        nullable=False,
        index=True,
    )

    # Relationships
    matched_content: Mapped[Optional["RegisteredContent"]] = relationship(
        "RegisteredContent",
        back_populates="verification_attempts",
    )

    __table_args__ = (
        Index("idx_verification_attempts_hash_verdict", "submitted_hash", "verdict"),
        Index("idx_verification_attempts_matched_content", "matched_content_id"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert VerificationAttempt model to dictionary."""
        return {
            "id": str(self.id) if self.id else None,
            "submitted_hash": self.submitted_hash,
            "matched_content_id": str(self.matched_content_id) if self.matched_content_id else None,
            "verdict": self.verdict.value if isinstance(self.verdict, enum.Enum) else self.verdict,
            "evidence_bundle": self.evidence_bundle,
            "confidence_score": self.confidence_score,
            "verification_time_ms": self.verification_time_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<VerificationAttempt(id={self.id}, hash='{self.submitted_hash[:8]}...', "
            f"verdict='{self.verdict.value if isinstance(self.verdict, enum.Enum) else self.verdict}', "
            f"confidence={self.confidence_score})>"
        )


# ============================================================================
# 8. DomainWhitelist Model
# ============================================================================

class DomainWhitelist(Base):
    __tablename__ = "domain_whitelists"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    domain: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    allowed_roles: Mapped[List[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utc_now,
        nullable=False,
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert DomainWhitelist model to dictionary."""
        return {
            "id": str(self.id) if self.id else None,
            "domain": self.domain,
            "allowed_roles": self.allowed_roles,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<DomainWhitelist(id={self.id}, domain='{self.domain}', "
            f"allowed_roles={self.allowed_roles}, is_active={self.is_active})>"
        )
