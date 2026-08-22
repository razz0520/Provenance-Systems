"""Admin and System Monitoring Endpoints."""

import logging
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.core.hash_service import detect_tampering, verify_chain
from app.models.database import (
    AuditLog,
    CryptographicManifest,
    HashChainEntry,
    RegisteredContent,
    User,
    UserRole,
    VerificationAttempt,
    VerificationVerdict,
)
from app.schemas import (
    AuditLogResponse,
    SystemStatsResponse,
    UpdateUserRoleRequest,
    UserResponse,
)
from app.services.auth_service import assign_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin Operations"], dependencies=[Depends(require_admin)])


@router.get(
    "/users",
    response_model=List[UserResponse],
    summary="List all registered platform users",
)
def list_users(
    role: Optional[UserRole] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Any:
    """List system users with optional role filtering (Admin only)."""
    query = select(User)
    if role:
        query = query.where(User.role == role)

    users = db.execute(query.order_by(desc(User.created_at)).offset(skip).limit(limit)).scalars().all()
    return [u.to_dict() for u in users]


@router.put(
    "/users/{id}/role",
    response_model=UserResponse,
    summary="Modify user role permissions",
)
def update_user_role(
    id: str,
    payload: UpdateUserRoleRequest,
    db: Session = Depends(get_db),
) -> Any:
    """Elevate or modify user role (Admin only)."""
    try:
        user = assign_role(db, user_id=id, role=payload.role)
        return user.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/audit-logs",
    response_model=List[AuditLogResponse],
    summary="View system audit trail",
)
def view_audit_logs(
    action: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> Any:
    """Query immutable audit events (Admin only)."""
    query = select(AuditLog)
    if action:
        query = query.where(AuditLog.action == action)

    logs = db.execute(query.order_by(desc(AuditLog.created_at)).offset(skip).limit(limit)).scalars().all()
    return [log.to_dict() for log in logs]


@router.get(
    "/stats",
    response_model=SystemStatsResponse,
    summary="Get aggregated provenance system statistics",
)
def system_statistics(db: Session = Depends(get_db)) -> Any:
    """Retrieve global platform statistics and ledger health."""
    total_users = len(db.execute(select(User)).scalars().all())
    total_publishers = len(db.execute(select(User).where(User.role == UserRole.PUBLISHER)).scalars().all())
    total_content = len(db.execute(select(RegisteredContent)).scalars().all())
    total_manifests = len(db.execute(select(CryptographicManifest)).scalars().all())
    total_blocks = len(db.execute(select(HashChainEntry)).scalars().all())
    total_verifications = len(db.execute(select(VerificationAttempt)).scalars().all())

    # Verifications breakdown
    verdict_counts: Dict[str, int] = {v.value: 0 for v in VerificationVerdict}
    verdict_results = db.execute(
        select(VerificationAttempt.verdict, func.count(VerificationAttempt.id))
        .group_by(VerificationAttempt.verdict)
    ).all()

    for v_enum, count in verdict_results:
        verdict_counts[v_enum.value if hasattr(v_enum, "value") else str(v_enum)] = count

    # Hash chain integrity check
    chain_valid, _ = verify_chain(db)

    return {
        "total_users": total_users,
        "total_publishers": total_publishers,
        "total_registered_content": total_content,
        "total_manifests": total_manifests,
        "total_chain_blocks": total_blocks,
        "total_verifications": total_verifications,
        "verifications_by_verdict": verdict_counts,
        "chain_integrity_valid": chain_valid,
    }
