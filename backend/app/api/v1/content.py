"""Content Management and Registration Endpoints."""

import json
import logging
from typing import Any, List, Optional
import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_publisher
from app.models.database import ContentStatus, ContentType, RegisteredContent, User
from app.schemas import (
    ContentListResponse,
    ContentRegisterResponse,
    ContentResponse,
    RevokeContentRequest,
    SupersedeContentRequest,
)
from app.services.publisher_service import (
    get_content,
    list_content,
    register_content,
    revoke_content,
    supersede_content,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/content", tags=["Content Management"])


@router.post(
    "/register",
    response_model=ContentRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register official content (Publisher)",
)
def register_content_endpoint(
    file: UploadFile = File(...),
    metadata: Optional[str] = Form(None),
    private_key: Optional[str] = Form(None),
    current_user: User = Depends(require_publisher),
    db: Session = Depends(get_db),
) -> Any:
    """
    Register and sign official government content with Ed25519 digital signature
    and anchor it into the tamper-resistant provenance hash chain.
    """
    parsed_metadata = {}
    if metadata:
        try:
            parsed_metadata = json.loads(metadata)
        except Exception:
            parsed_metadata = {"raw": metadata}

    try:
        registered = register_content(
            db=db,
            publisher=current_user,
            upload_file=file,
            metadata=parsed_metadata,
            private_key_pem=private_key,
        )

        manifest = registered.manifest
        chain_entry = registered.hash_chain_entry

        return {
            "content_id": str(registered.id),
            "publisher_id": str(registered.publisher_id),
            "sha256_hash": registered.sha256_hash,
            "content_type": registered.content_type.value,
            "original_filename": registered.original_filename,
            "file_size": registered.file_size,
            "manifest_signature": manifest.digital_signature if manifest else "",
            "hash_chain_block_id": chain_entry.id if chain_entry else 0,
            "created_at": registered.created_at.isoformat(),
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Content registration error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Content registration failed: {e}",
        )


@router.get(
    "/{content_id}",
    response_model=ContentResponse,
    summary="Retrieve registered content details",
)
def get_content_by_id(
    content_id: str,
    db: Session = Depends(get_db),
) -> Any:
    """Get metadata, cryptographic hashes, and provenance status of registered content."""
    try:
        content = get_content(db, content_id)
        if not content:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Content not found with ID {content_id}",
            )
        return content.to_dict()
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid content ID format")


@router.get(
    "",
    response_model=ContentListResponse,
    summary="List registered content with filters and pagination",
)
def list_contents(
    publisher_id: Optional[str] = Query(None),
    content_type: Optional[ContentType] = Query(None),
    status_filter: Optional[ContentStatus] = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Any:
    """Search and browse official registered provenance items."""
    items, total = list_content(
        db=db,
        publisher_id=publisher_id,
        content_type=content_type,
        status=status_filter,
        skip=skip,
        limit=limit,
    )
    return {
        "total": total,
        "items": [item.to_dict() for item in items],
    }


@router.put(
    "/{content_id}/supersede",
    response_model=ContentResponse,
    summary="Supersede content with an updated version",
)
def supersede_content_endpoint(
    content_id: str,
    new_content_id: str = Query(...),
    payload: Optional[SupersedeContentRequest] = None,
    current_user: User = Depends(require_publisher),
    db: Session = Depends(get_db),
) -> Any:
    """Mark an existing content item as superseded by a newer version."""
    reason = payload.reason if payload else "Superseded by updated version"
    try:
        updated = supersede_content(
            db=db,
            old_content_id=content_id,
            new_content_id=new_content_id,
            actor=current_user,
            reason=reason,
        )
        return updated.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put(
    "/{content_id}/revoke",
    response_model=ContentResponse,
    summary="Revoke official content status",
)
def revoke_content_endpoint(
    content_id: str,
    payload: RevokeContentRequest,
    current_user: User = Depends(require_publisher),
    db: Session = Depends(get_db),
) -> Any:
    """Revoke official validity of registered content (e.g., retracted publication)."""
    try:
        revoked = revoke_content(
            db=db,
            content_id=content_id,
            actor=current_user,
            reason=payload.reason,
        )
        return revoked.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
