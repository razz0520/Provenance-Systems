"""Publisher Credential Management Endpoints."""

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_publisher
from app.models.database import (
    AuditLog,
    Credential,
    CredentialStatus,
    CredentialType,
    User,
    UserRole,
)
from app.schemas import (
    CreateCredentialRequest,
    CredentialResponse,
    RevokeCredentialRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/credentials", tags=["Credentials"])


@router.get(
    "",
    response_model=List[CredentialResponse],
    summary="List publisher credentials",
)
def list_credentials(
    publisher_id: Optional[str] = Query(None),
    status_filter: Optional[CredentialStatus] = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """List active and historical credentials for publishers."""
    query = select(Credential)

    # Publishers can only view their own credentials unless Admin
    if current_user.role != UserRole.ADMIN:
        query = query.where(Credential.publisher_id == current_user.id)
    elif publisher_id:
        pid = uuid.UUID(publisher_id)
        query = query.where(Credential.publisher_id == pid)

    if status_filter:
        query = query.where(Credential.status == status_filter)

    credentials = db.execute(query.order_by(desc(Credential.created_at))).scalars().all()
    return [c.to_dict() for c in credentials]


@router.post(
    "",
    response_model=CredentialResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Issue a new publisher credential",
)
def create_credential(
    payload: CreateCredentialRequest,
    current_user: User = Depends(require_publisher),
    db: Session = Depends(get_db),
) -> Any:
    """Issue a new signing credential for a publisher."""
    target_publisher_id = current_user.id
    if payload.publisher_id and current_user.role == UserRole.ADMIN:
        target_publisher_id = uuid.UUID(payload.publisher_id)

    now = datetime.now(timezone.utc)
    valid_until = now + timedelta(days=payload.valid_days)

    credential = Credential(
        publisher_id=target_publisher_id,
        credential_type=payload.credential_type,
        status=CredentialStatus.ACTIVE,
        valid_from=now,
        valid_until=valid_until,
    )
    db.add(credential)
    db.flush()

    audit = AuditLog(
        actor_id=current_user.id,
        action="CREDENTIAL_CREATED",
        details={"credential_id": str(credential.id), "type": payload.credential_type.value},
    )
    db.add(audit)
    db.commit()
    db.refresh(credential)

    return credential.to_dict()


@router.put(
    "/{id}/revoke",
    response_model=CredentialResponse,
    summary="Revoke a publisher credential",
)
def revoke_credential(
    id: str,
    payload: RevokeCredentialRequest,
    current_user: User = Depends(require_publisher),
    db: Session = Depends(get_db),
) -> Any:
    """Permanently revoke a publisher credential."""
    cid = uuid.UUID(id)
    cred = db.execute(select(Credential).where(Credential.id == cid)).scalar_one_or_none()

    if not cred:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")

    if current_user.role != UserRole.ADMIN and cred.publisher_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized")

    cred.status = CredentialStatus.REVOKED
    cred.revoked_at = datetime.now(timezone.utc)
    cred.revocation_reason = payload.reason

    audit = AuditLog(
        actor_id=current_user.id,
        action="CREDENTIAL_REVOKED",
        details={"credential_id": str(cred.id), "reason": payload.reason},
    )
    db.add(audit)
    db.commit()
    db.refresh(cred)

    return cred.to_dict()


@router.put(
    "/{id}/suspend",
    response_model=CredentialResponse,
    summary="Suspend a publisher credential",
)
def suspend_credential(
    id: str,
    current_user: User = Depends(require_publisher),
    db: Session = Depends(get_db),
) -> Any:
    """Temporarily suspend a publisher credential."""
    cid = uuid.UUID(id)
    cred = db.execute(select(Credential).where(Credential.id == cid)).scalar_one_or_none()

    if not cred:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")

    if current_user.role != UserRole.ADMIN and cred.publisher_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized")

    cred.status = CredentialStatus.SUSPENDED

    audit = AuditLog(
        actor_id=current_user.id,
        action="CREDENTIAL_SUSPENDED",
        details={"credential_id": str(cred.id)},
    )
    db.add(audit)
    db.commit()
    db.refresh(cred)

    return cred.to_dict()
