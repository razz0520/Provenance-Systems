"""Pydantic V2 Schemas for FastAPI Request/Response Validation."""

from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.database import (
    ContentStatus,
    ContentType,
    CredentialStatus,
    CredentialType,
    UserRole,
    VerificationVerdict,
)


# ============================================================================
# Common Schemas
# ============================================================================

class MessageResponse(BaseModel):
    message: str
    success: bool = True
    data: Optional[Dict[str, Any]] = None


class HealthResponse(BaseModel):
    status: str = "ok"
    database: str
    redis: str
    timestamp: datetime


class StatusResponse(BaseModel):
    status: str = "operational"
    version: str = "1.0.0"
    environment: str = "production"
    active_publishers: int
    total_registered_content: int
    total_verifications: int
    registry_integrity: bool


# ============================================================================
# Auth Schemas
# ============================================================================

class RegisterPublisherRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    organization_name: str = Field("Government Authority", min_length=2)
    organization_domain: Optional[str] = None
    department: Optional[str] = None
    designation: Optional[str] = None


class RegisterAdminRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    organization_name: str = "National Provenance Authority"
    organization_domain: str = "gov.in"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleAuthRequest(BaseModel):
    code: str
    redirect_uri: Optional[str] = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class MfaSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str
    backup_codes: List[str]


class MfaVerifyRequest(BaseModel):
    code: str
    secret: Optional[str] = None
    user_id: Optional[str] = None


class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    organization_name: str
    organization_domain: str
    department: Optional[str] = None
    designation: Optional[str] = None
    public_key: Optional[str] = None
    is_active: bool
    is_verified: bool
    mfa_enabled: bool
    login_count: int
    created_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    mfa_required: bool = False
    mfa_session_token: Optional[str] = None
    user: Optional[UserResponse] = None


class UpdateProfileRequest(BaseModel):
    organization_name: Optional[str] = None
    department: Optional[str] = None
    designation: Optional[str] = None
    password: Optional[str] = Field(None, min_length=8)


# ============================================================================
# Content Schemas
# ============================================================================

class ContentRegisterResponse(BaseModel):
    content_id: str
    publisher_id: str
    sha256_hash: str
    content_type: str
    original_filename: str
    file_size: int
    manifest_signature: str
    hash_chain_block_id: int
    created_at: str


class ContentResponse(BaseModel):
    id: str
    publisher_id: str
    credential_id: str
    content_type: str
    original_filename: str
    stored_filename: str
    sha256_hash: str
    perceptual_hash: Dict[str, Any]
    watermark_data: Optional[Dict[str, Any]] = None
    file_size: int
    mime_type: str
    duration_seconds: Optional[float] = None
    status: str
    superseded_by_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ContentListResponse(BaseModel):
    total: int
    items: List[ContentResponse]


class SupersedeContentRequest(BaseModel):
    reason: Optional[str] = None


class RevokeContentRequest(BaseModel):
    reason: str = Field(..., min_length=3)


# ============================================================================
# Verification Schemas
# ============================================================================

class VerifyTextRequest(BaseModel):
    text: str = Field(..., min_length=1)


class EvidenceBundle(BaseModel):
    match_type: str  # "EXACT_SHA256", "PERCEPTUAL_SIMILARITY", "NONE"
    sha256_submitted: str
    matched_hash: Optional[str] = None
    similarity_score: float = 0.0
    publisher_name: Optional[str] = None
    publisher_domain: Optional[str] = None
    publisher_public_key: Optional[str] = None
    digital_signature: Optional[str] = None
    signature_valid: bool = False
    manifest_valid: bool = False
    chain_block_id: Optional[int] = None
    chain_integrity: bool = False
    content_metadata: Optional[Dict[str, Any]] = None


class VerificationResponse(BaseModel):
    verification_id: str
    submitted_hash: str
    verdict: str  # 'VERIFIED', 'SUSPICIOUS', 'UNSIGNED', 'PROVEN_INVALID'
    confidence_score: float
    verification_time_ms: int
    matched_content: Optional[ContentResponse] = None
    evidence_bundle: EvidenceBundle
    created_at: str


# ============================================================================
# Credential Schemas
# ============================================================================

class CreateCredentialRequest(BaseModel):
    publisher_id: Optional[str] = None
    credential_type: CredentialType = CredentialType.SECONDARY
    valid_days: int = Field(365, ge=1, le=1825)


class CredentialResponse(BaseModel):
    id: str
    publisher_id: str
    credential_type: str
    status: str
    valid_from: str
    valid_until: str
    revoked_at: Optional[str] = None
    revocation_reason: Optional[str] = None
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class RevokeCredentialRequest(BaseModel):
    reason: str = Field(..., min_length=3)


# ============================================================================
# Admin & Audit Schemas
# ============================================================================

class UpdateUserRoleRequest(BaseModel):
    role: UserRole


class AuditLogResponse(BaseModel):
    id: str
    actor_id: Optional[str] = None
    action: str
    details: Dict[str, Any]
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class SystemStatsResponse(BaseModel):
    total_users: int
    total_publishers: int
    total_registered_content: int
    total_manifests: int
    total_chain_blocks: int
    total_verifications: int
    verifications_by_verdict: Dict[str, int]
    chain_integrity_valid: bool


class IntegrityStatusResponse(BaseModel):
    is_valid: bool
    total_blocks: int
    genesis_hash: str
    latest_hash: str
    broken_index: Optional[int] = None
    last_verified_at: str
