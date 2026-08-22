"""FastAPI Request Dependencies and Security Guards."""

from typing import Callable, Generator, Optional
import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import check_rate_limit, decode_token, is_token_blacklisted, verify_token
from app.database import SessionLocal
from app.models.database import User, UserRole

# Reusable Bearer Auth Scheme
oauth2_scheme = HTTPBearer(auto_error=True)
oauth2_scheme_optional = HTTPBearer(auto_error=False)

ROLE_HIERARCHY = {
    UserRole.VIEWER: 1,
    UserRole.PUBLISHER: 2,
    UserRole.ADMIN: 3,
}


def get_db() -> Generator[Session, None, None]:
    """Provide a database session for request lifecycle."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    auth: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Extract and validate JWT token from Authorization header and return active User.

    Raises:
        HTTPException: 401 if token is invalid, expired, revoked, or user inactive.
    """
    token = auth.credentials
    try:
        payload = verify_token(token, expected_type="access")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check for MFA pending
    if payload.get("mfa_pending"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MFA authentication pending",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID format in token",
        )

    user = db.execute(select(User).where(User.id == uid)).scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    return user


def get_current_user_optional(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Optionally extract current user if Authorization header is present."""
    if not auth:
        return None
    try:
        return get_current_user(auth, db)
    except HTTPException:
        return None


def require_role(required_role: UserRole) -> Callable:
    """
    Dependency factory to enforce role hierarchy permissions.
    ADMIN > PUBLISHER > VIEWER
    """
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        user_level = ROLE_HIERARCHY.get(current_user.role, 0)
        required_level = ROLE_HIERARCHY.get(required_role, 0)

        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation requires {required_role.value} privileges",
            )
        return current_user

    return role_checker


# Role Guard Shortcuts
require_admin = require_role(UserRole.ADMIN)
require_publisher = require_role(UserRole.PUBLISHER)
require_viewer = require_role(UserRole.VIEWER)


def rate_limiter(max_requests: int = 60, window_seconds: int = 60) -> Callable:
    """Rate limiting dependency per client IP."""
    def check_limit(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path
        rate_key = f"ip:{client_ip}:{path}"

        if not check_rate_limit(rate_key, max_requests=max_requests, window_seconds=window_seconds):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please slow down.",
            )

    return check_limit
