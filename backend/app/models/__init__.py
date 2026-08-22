"""Database models package.

Exports all SQLAlchemy 2.0 declarative models and enums for the
Deepfake-Resistant Provenance & Verification System.
"""

from app.models.database import (
    AuditLog,
    Base,
    ContentStatus,
    ContentType,
    Credential,
    CredentialStatus,
    CredentialType,
    CryptographicManifest,
    DomainWhitelist,
    HashChainEntry,
    RegisteredContent,
    User,
    UserRole,
    VerificationAttempt,
    VerificationVerdict,
)

__all__ = [
    # Base
    "Base",
    # Models
    "User",
    "Credential",
    "RegisteredContent",
    "CryptographicManifest",
    "HashChainEntry",
    "AuditLog",
    "VerificationAttempt",
    "DomainWhitelist",
    # Enums
    "UserRole",
    "CredentialType",
    "CredentialStatus",
    "ContentType",
    "ContentStatus",
    "VerificationVerdict",
]
