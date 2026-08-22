"""Authentication API Endpoints."""

import logging
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, rate_limiter
from app.core.security import (
    generate_backup_codes,
    generate_totp_secret,
    get_google_auth_url,
    get_totp_uri,
    verify_totp,
)
from app.models.database import User
from app.schemas import (
    GoogleAuthRequest,
    LoginRequest,
    MessageResponse,
    MfaSetupResponse,
    MfaVerifyRequest,
    RefreshTokenRequest,
    RegisterPublisherRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth_service import (
    authenticate_user,
    authenticate_with_google,
    logout_user,
    refresh_tokens,
    register_publisher,
    verify_mfa_login,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limiter(max_requests=10, window_seconds=60))],
    summary="Register a new official publisher",
)
def register(
    payload: RegisterPublisherRequest,
    db: Session = Depends(get_db),
) -> Any:
    """Register a new publisher account with Ed25519 cryptographic key generation."""
    try:
        domain = payload.organization_domain or payload.email.split("@")[-1]
        user = register_publisher(
            db=db,
            email=payload.email,
            password=payload.password,
            organization_name=payload.organization_name,
            organization_domain=domain,
            department=payload.department,
            designation=payload.designation,
        )
        return user.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limiter(max_requests=15, window_seconds=60))],
    summary="Authenticate with email and password",
)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> Any:
    """Authenticate a user and return access/refresh tokens or prompt for MFA."""
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    try:
        result = authenticate_user(
            db=db,
            email=payload.email,
            password=payload.password,
            ip_address=client_ip,
            user_agent=user_agent,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.get(
    "/google",
    summary="Get Google OAuth authorization URL",
)
def google_auth_url() -> Dict[str, str]:
    """Retrieve Google OAuth 2.0 redirect URL."""
    url = get_google_auth_url()
    return {"url": url}


@router.post(
    "/google",
    response_model=TokenResponse,
    summary="Authenticate via Google OAuth authorization code",
)
def google_auth(
    payload: GoogleAuthRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> Any:
    """Exchange Google OAuth code for JWT session tokens."""
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    try:
        result = authenticate_with_google(
            db=db,
            code=payload.code,
            redirect_uri=payload.redirect_uri,
            ip_address=client_ip,
            user_agent=user_agent,
        )
        return result
    except Exception as e:
        logger.error("Google OAuth failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google authentication failed: {e}",
        )


@router.post(
    "/google/callback",
    response_model=TokenResponse,
    summary="Google OAuth callback handler",
)
def google_callback(
    payload: GoogleAuthRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> Any:
    """Alternative callback handler for Google OAuth redirect."""
    return google_auth(payload=payload, request=request, db=db)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token with refresh token rotation",
)
def refresh_token_endpoint(
    payload: RefreshTokenRequest,
    db: Session = Depends(get_db),
) -> Any:
    """Exchange valid refresh token for a fresh token pair."""
    try:
        tokens = refresh_tokens(db=db, refresh_token=payload.refresh_token)
        return tokens
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Logout and revoke active session token",
)
def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Blacklist the active bearer token and close session."""
    auth_header = request.headers.get("authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    logout_user(token=token, user_id=current_user.id, db=db)
    return {"message": "Logged out successfully", "success": True}


@router.post(
    "/mfa/setup",
    response_model=MfaSetupResponse,
    summary="Initialize TOTP Multi-Factor Authentication",
)
def setup_mfa(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Generate TOTP secret and provisioning URI for Google Authenticator."""
    secret = generate_totp_secret()
    otpauth_uri = get_totp_uri(secret, email=current_user.email)
    backup_codes = generate_backup_codes(count=8)

    current_user.mfa_secret = secret
    db.commit()

    return {
        "secret": secret,
        "otpauth_uri": otpauth_uri,
        "backup_codes": backup_codes,
    }


@router.post(
    "/mfa/verify",
    response_model=TokenResponse,
    summary="Verify TOTP code to activate MFA or complete login",
)
def verify_mfa(
    payload: MfaVerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> Any:
    """Verify 6-digit TOTP code and activate MFA for user."""
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    if payload.user_id:
        try:
            return verify_mfa_login(
                db=db,
                user_id=payload.user_id,
                totp_code=payload.code,
                ip_address=client_ip,
                user_agent=user_agent,
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    auth_header = request.headers.get("authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization token required")

    from app.core.security import decode_token
    claims = decode_token(token)
    user_id = claims.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.mfa_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA setup has not been initiated")

    if not verify_totp(user.mfa_secret, payload.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid 6-digit code")

    user.mfa_enabled = True
    db.commit()

    return {
        "mfa_required": False,
        "user": user.to_dict(),
        "token_type": "bearer",
    }
