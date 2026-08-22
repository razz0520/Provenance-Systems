"""System Health, Status, and Registry Integrity Endpoints."""

from datetime import datetime, timezone
import logging
from typing import Any
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.hash_service import get_chain_state, verify_chain
from app.core.security import get_redis_client
from app.database import check_db_connection
from app.models.database import RegisteredContent, User, UserRole, VerificationAttempt
from app.schemas import HealthResponse, IntegrityStatusResponse, StatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["System"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check for database, redis, and backend services",
)
def health_check() -> Any:
    """Verify operational health of backend, database, and Redis."""
    db_ok = check_db_connection()
    redis_client = get_redis_client()
    redis_ok = False
    if redis_client:
        try:
            redis_ok = bool(redis_client.ping())
        except Exception:
            redis_ok = False

    return {
        "status": "ok" if db_ok and redis_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "redis": "connected" if redis_ok else "disconnected",
        "timestamp": datetime.now(timezone.utc),
    }


@router.get(
    "/api/v1/status",
    response_model=StatusResponse,
    summary="High-level provenance system status",
)
def system_status(db: Session = Depends(get_db)) -> Any:
    """Get operational summary and integrity flag."""
    active_pub = len(
        db.execute(select(User).where((User.role == UserRole.PUBLISHER) & (User.is_active.is_(True))))
        .scalars()
        .all()
    )
    total_content = len(db.execute(select(RegisteredContent)).scalars().all())
    total_verif = len(db.execute(select(VerificationAttempt)).scalars().all())
    is_valid, _ = verify_chain(db)

    return {
        "status": "operational" if is_valid else "compromised",
        "version": "1.0.0",
        "environment": "production",
        "active_publishers": active_pub,
        "total_registered_content": total_content,
        "total_verifications": total_verif,
        "registry_integrity": is_valid,
    }


@router.get(
    "/api/v1/registry/integrity",
    response_model=IntegrityStatusResponse,
    summary="Verify immutable hash chain integrity",
)
def registry_integrity(db: Session = Depends(get_db)) -> Any:
    """Comprehensive hash chain cryptographic verification from genesis block to head."""
    state = get_chain_state(db)
    return {
        "is_valid": state["is_valid"],
        "total_blocks": state["total_blocks"],
        "genesis_hash": state["genesis_hash"],
        "latest_hash": state["latest_hash"],
        "broken_index": state.get("broken_index"),
        "last_verified_at": datetime.now(timezone.utc).isoformat(),
    }
