"""Security, Authentication, and Cryptographic Token Utilities.

Provides password hashing, JWT generation/verification, Google OAuth integration,
TOTP Multi-Factor Authentication, token blacklisting, and rate limiting.
"""

from datetime import datetime, timedelta, timezone
import json
import logging
import secrets
import string
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

import httpx
from jose import JWTError, jwt
from passlib.context import CryptContext
import pyotp
import redis

from app.config import settings
from app.models.database import UserRole

logger = logging.getLogger(__name__)

import bcrypt
# Patch for passlib compatibility with bcrypt >= 4.0.0
if not hasattr(bcrypt, "__about__"):
    class _BcryptAbout:
        __version__ = getattr(bcrypt, "__version__", "4.0.0")
    bcrypt.__about__ = _BcryptAbout

# Password Hashing Context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Redis Connection with fallback to memory
_redis_client: Optional[redis.Redis] = None
_in_memory_blacklist: Dict[str, datetime] = {}
_in_memory_rate_limits: Dict[str, List[datetime]] = {}
_in_memory_failed_logins: Dict[str, Dict[str, Any]] = {}


def get_redis_client() -> Optional[redis.Redis]:
    """Get or initialize Redis connection."""
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=2,
            )
            _redis_client.ping()
            logger.info("Connected to Redis cache for auth security")
        except Exception as e:
            logger.warning("Redis connection failed, using in-memory auth cache fallback: %s", e)
            _redis_client = None
    return _redis_client


# ============================================================================
# 1. Password Security
# ============================================================================

def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: Optional[str]) -> bool:
    """Verify a plaintext password against its bcrypt hash."""
    if not hashed_password or not plain_password:
        return False
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        logger.warning("Error verifying password hash: %s", e)
        return False


def generate_secure_token(length: int = 32) -> str:
    """Generate a cryptographically secure URL-safe random token."""
    return secrets.token_urlsafe(length)


# ============================================================================
# 2. JWT Management & Blacklisting
# ============================================================================

def create_access_token(
    user_id: Union[str, uuid.UUID],
    role: Union[str, UserRole],
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Create a signed JWT access token.

    Args:
        user_id: UUID or identifier of user.
        role: User role.
        expires_delta: Optional custom token expiration time.
        extra_claims: Additional custom claims to include in the payload.

    Returns:
        Encoded JWT token string.
    """
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    role_str = role.value if isinstance(role, UserRole) else str(role)
    token_jti = str(uuid.uuid4())

    to_encode: Dict[str, Any] = {
        "sub": str(user_id),
        "role": role_str,
        "type": "access",
        "jti": token_jti,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if extra_claims:
        to_encode.update(extra_claims)

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def create_refresh_token(
    user_id: Union[str, uuid.UUID],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a signed JWT refresh token.

    Args:
        user_id: UUID or identifier of user.
        expires_delta: Optional custom token expiration time.

    Returns:
        Encoded JWT refresh token string.
    """
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    token_jti = str(uuid.uuid4())
    to_encode = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": token_jti,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def blacklist_token(token: str, expiry_seconds: Optional[int] = None) -> bool:
    """
    Add a token JTI to the blacklist cache to prevent further usage.

    Args:
        token: JWT token string.
        expiry_seconds: TTL in seconds. Defaults to token's remaining time.

    Returns:
        True if blacklisted.
    """
    try:
        payload = decode_token(token, verify_exp=False)
        jti = payload.get("jti")
        if not jti:
            return False

        if expiry_seconds is None:
            exp = payload.get("exp")
            if exp:
                remaining = int(exp - datetime.now(timezone.utc).timestamp())
                expiry_seconds = max(remaining, 60)
            else:
                expiry_seconds = 3600

        r = get_redis_client()
        if r:
            r.setex(f"blacklist:token:{jti}", expiry_seconds, "revoked")
        else:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expiry_seconds)
            _in_memory_blacklist[jti] = expires_at

        logger.info("Blacklisted token JTI %s for %s seconds", jti, expiry_seconds)
        return True
    except Exception as e:
        logger.error("Failed to blacklist token: %s", e)
        return False


def is_token_blacklisted(jti_or_token: str) -> bool:
    """Check if token JTI is blacklisted."""
    try:
        jti = jti_or_token
        if "." in jti_or_token:
            payload = decode_token(jti_or_token, verify_exp=False)
            jti = payload.get("jti", "")

        if not jti:
            return False

        r = get_redis_client()
        if r:
            return bool(r.exists(f"blacklist:token:{jti}"))

        # In-memory check
        now = datetime.now(timezone.utc)
        if jti in _in_memory_blacklist:
            if _in_memory_blacklist[jti] > now:
                return True
            else:
                del _in_memory_blacklist[jti]
        return False
    except Exception as e:
        logger.warning("Error checking token blacklist: %s", e)
        return False


def decode_token(token: str, verify_exp: bool = True) -> Dict[str, Any]:
    """
    Decode and validate a JWT token.

    Args:
        token: JWT string.
        verify_exp: Whether to verify token expiration.

    Returns:
        Decoded claims dictionary.

    Raises:
        ValueError: If token is invalid or expired.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_exp": verify_exp},
        )
        return payload
    except JWTError as e:
        logger.debug("JWT decode error: %s", e)
        raise ValueError(f"Invalid or expired token: {e}") from e


def verify_token(token: str, expected_type: Optional[str] = "access") -> Dict[str, Any]:
    """
    Verify token validity, signature, expiration, type, and blacklist status.

    Args:
        token: JWT string.
        expected_type: Expected 'type' claim ('access' or 'refresh').

    Returns:
        Token claims dictionary.

    Raises:
        ValueError: If token is revoked, expired, or invalid.
    """
    payload = decode_token(token, verify_exp=True)

    if is_token_blacklisted(payload.get("jti", "")):
        raise ValueError("Token has been revoked")

    if expected_type and payload.get("type") != expected_type:
        raise ValueError(f"Invalid token type. Expected '{expected_type}', got '{payload.get('type')}'")

    return payload


# ============================================================================
# 3. Google OAuth Service
# ============================================================================

def get_google_auth_url(
    state: Optional[str] = None,
    redirect_uri: Optional[str] = None,
) -> str:
    """
    Generate Google OAuth 2.0 authorization URL.

    Args:
        state: CSRF state parameter.
        redirect_uri: Custom redirect URI override.

    Returns:
        Google authorization URL.
    """
    r_uri = redirect_uri or settings.GOOGLE_REDIRECT_URI
    scopes = "openid email profile"
    state_param = f"&state={state}" if state else ""

    url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={settings.GOOGLE_CLIENT_ID}&"
        f"redirect_uri={r_uri}&"
        f"response_type=code&"
        f"scope={scopes}&"
        f"access_type=offline&"
        f"prompt=consent{state_param}"
    )
    return url


def exchange_code_for_tokens(
    code: str,
    redirect_uri: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Exchange OAuth authorization code for Google tokens.

    Args:
        code: Authorization code from Google redirect.
        redirect_uri: Redirect URI used during auth request.

    Returns:
        Token response dictionary containing access_token, id_token, etc.
    """
    r_uri = redirect_uri or settings.GOOGLE_REDIRECT_URI
    token_endpoint = "https://oauth2.googleapis.com/token"

    payload = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": r_uri,
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(token_endpoint, data=payload)
            if response.status_code != 200:
                logger.error("Google token exchange failed: %s", response.text)
                raise ValueError(f"Google OAuth error: {response.text}")
            return response.json()
    except Exception as e:
        logger.error("Failed to exchange Google OAuth code: %s", e)
        raise


def verify_google_id_token(id_token: str) -> Dict[str, Any]:
    """
    Verify Google ID Token via Google's tokeninfo endpoint.

    Args:
        id_token: Google OpenID Connect ID token.

    Returns:
        Token claims dictionary.
    """
    endpoint = "https://oauth2.googleapis.com/tokeninfo"
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(endpoint, params={"id_token": id_token})
            if response.status_code != 200:
                raise ValueError(f"Invalid Google ID token: {response.text}")
            data = response.json()
            if settings.GOOGLE_CLIENT_ID and data.get("aud") != settings.GOOGLE_CLIENT_ID:
                raise ValueError("Google ID token audience mismatch")
            return data
    except Exception as e:
        logger.error("Google ID token verification failed: %s", e)
        raise


def get_google_user_info(access_token: str) -> Dict[str, Any]:
    """
    Retrieve user profile info from Google UserInfo endpoint.

    Args:
        access_token: Google OAuth access token.

    Returns:
        Dictionary with email, sub, name, picture, email_verified.
    """
    endpoint = "https://www.googleapis.com/oauth2/v3/userinfo"
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if response.status_code != 200:
                raise ValueError(f"Could not fetch Google userinfo: {response.text}")
            return response.json()
    except Exception as e:
        logger.error("Failed to fetch Google userinfo: %s", e)
        raise


# ============================================================================
# 4. Multi-Factor Authentication (TOTP)
# ============================================================================

def generate_totp_secret() -> str:
    """Generate a random Base32 secret for TOTP (Google Authenticator)."""
    return pyotp.random_base32()


def get_totp_uri(secret: str, email: str, issuer: str = "Deepfake Provenance") -> str:
    """Generate the standard otpauth URI for QR code generation."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=issuer)


def verify_totp(secret: str, code: str, valid_window: int = 1) -> bool:
    """
    Verify a 6-digit TOTP code against the secret.

    Args:
        secret: Base32 secret string.
        code: 6-digit verification code.
        valid_window: Accept codes from +/- N time intervals (default 1 = 30s window).

    Returns:
        True if code is valid, False otherwise.
    """
    if not secret or not code:
        return False
    try:
        clean_code = str(code).strip().replace(" ", "")
        totp = pyotp.TOTP(secret)
        return bool(totp.verify(clean_code, valid_window=valid_window))
    except Exception as e:
        logger.warning("TOTP verification error: %s", e)
        return False


def generate_backup_codes(count: int = 8, length: int = 8) -> List[str]:
    """
    Generate alphanumeric single-use MFA backup codes.

    Args:
        count: Number of backup codes.
        length: Length of each code.

    Returns:
        List of formatted codes (e.g. ['A1B2-C3D4', ...]).
    """
    chars = string.ascii_uppercase + string.digits
    codes = []
    for _ in range(count):
        raw = "".join(secrets.choice(chars) for _ in range(length))
        formatted = f"{raw[:length//2]}-{raw[length//2:]}"
        codes.append(formatted)
    return codes


# ============================================================================
# 5. Rate Limiting & Account Lockout
# ============================================================================

def check_rate_limit(
    identifier: str,
    max_requests: int = 5,
    window_seconds: int = 60,
) -> bool:
    """
    Check if an identifier is within the allowed rate limit.

    Args:
        identifier: IP address, user email, or route key.
        max_requests: Maximum allowed attempts in window.
        window_seconds: Time window in seconds.

    Returns:
        True if request is allowed, False if limit exceeded.
    """
    r = get_redis_client()
    key = f"ratelimit:{identifier}"

    if r:
        try:
            current = r.get(key)
            if current and int(current) >= max_requests:
                return False
            return True
        except Exception:
            pass

    # In-memory rate limiting fallback
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=window_seconds)

    if identifier not in _in_memory_rate_limits:
        _in_memory_rate_limits[identifier] = []

    # Clean old requests
    _in_memory_rate_limits[identifier] = [
        t for t in _in_memory_rate_limits[identifier] if t > cutoff
    ]

    return len(_in_memory_rate_limits[identifier]) < max_requests


def increment_rate_counter(identifier: str, window_seconds: int = 60) -> int:
    """
    Increment request counter for an identifier.

    Args:
        identifier: IP or client key.
        window_seconds: Window expiration in seconds.

    Returns:
        Current count after increment.
    """
    r = get_redis_client()
    key = f"ratelimit:{identifier}"

    if r:
        try:
            val = r.incr(key)
            if val == 1:
                r.expire(key, window_seconds)
            return val
        except Exception:
            pass

    # In-memory fallback
    now = datetime.now(timezone.utc)
    if identifier not in _in_memory_rate_limits:
        _in_memory_rate_limits[identifier] = []
    _in_memory_rate_limits[identifier].append(now)
    return len(_in_memory_rate_limits[identifier])


def reset_rate_counter(identifier: str) -> None:
    """Reset rate limiting counter for an identifier."""
    r = get_redis_client()
    if r:
        try:
            r.delete(f"ratelimit:{identifier}")
        except Exception:
            pass
    _in_memory_rate_limits.pop(identifier, None)


def record_failed_login(
    identifier: str,
    max_attempts: int = 5,
    lockout_seconds: int = 900,
) -> Tuple[bool, int]:
    """
    Record a failed login attempt and check for account lockout.

    Args:
        identifier: Email or user identifier.
        max_attempts: Attempts threshold before lockout (default: 5).
        lockout_seconds: Lockout duration in seconds (default: 15 mins).

    Returns:
        Tuple of (is_locked_out: bool, remaining_attempts: int).
    """
    r = get_redis_client()
    key = f"failed_logins:{identifier}"
    lock_key = f"account_locked:{identifier}"

    if r:
        try:
            attempts = r.incr(key)
            if attempts == 1:
                r.expire(key, lockout_seconds)

            if attempts >= max_attempts:
                r.setex(lock_key, lockout_seconds, "locked")
                logger.warning("Account %s locked out due to %d failed attempts", identifier, attempts)
                return True, 0

            return False, max(0, max_attempts - attempts)
        except Exception:
            pass

    # In-memory fallback
    now = datetime.now(timezone.utc)
    if identifier not in _in_memory_failed_logins:
        _in_memory_failed_logins[identifier] = {"count": 0, "locked_until": None}

    entry = _in_memory_failed_logins[identifier]
    entry["count"] += 1

    if entry["count"] >= max_attempts:
        entry["locked_until"] = now + timedelta(seconds=lockout_seconds)
        return True, 0

    return False, max(0, max_attempts - entry["count"])


def is_account_locked(identifier: str) -> Tuple[bool, int]:
    """
    Check if an account identifier is currently locked out.

    Returns:
        Tuple of (is_locked: bool, remaining_lockout_seconds: int).
    """
    r = get_redis_client()
    lock_key = f"account_locked:{identifier}"

    if r:
        try:
            if r.exists(lock_key):
                ttl = r.ttl(lock_key)
                return True, max(0, ttl)
            return False, 0
        except Exception:
            pass

    # In-memory fallback
    now = datetime.now(timezone.utc)
    if identifier in _in_memory_failed_logins:
        locked_until = _in_memory_failed_logins[identifier].get("locked_until")
        if locked_until and locked_until > now:
            remaining = int((locked_until - now).total_seconds())
            return True, remaining

    return False, 0


def reset_failed_logins(identifier: str) -> None:
    """Clear failed login attempts and unlock account."""
    r = get_redis_client()
    if r:
        try:
            r.delete(f"failed_logins:{identifier}")
            r.delete(f"account_locked:{identifier}")
        except Exception:
            pass
    _in_memory_failed_logins.pop(identifier, None)
