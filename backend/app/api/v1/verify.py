"""Verification Endpoints for WhatsApp and Citizen Verification Portal."""

import logging
from typing import Any
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, rate_limiter
from app.schemas import VerificationResponse, VerifyTextRequest
from app.services.verification_service import (
    get_verification_result,
    verify_file,
    verify_text,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/verify", tags=["Verification"])


@router.post(
    "",
    response_model=VerificationResponse,
    dependencies=[Depends(rate_limiter(max_requests=30, window_seconds=60))],
    summary="Verify media file authenticity (Deepfake & Tampering Check)",
)
def verify_media_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> Any:
    """
    Public verification endpoint for media files.
    Calculates SHA-256 and perceptual fingerprints, cross-references the official
    provenance ledger, and verifies cryptographic signatures.
    """
    try:
        result = verify_file(db=db, upload_file=file)
        return result
    except Exception as e:
        logger.error("Media verification failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Verification process failed: {e}",
        )


@router.post(
    "/text",
    response_model=VerificationResponse,
    dependencies=[Depends(rate_limiter(max_requests=30, window_seconds=60))],
    summary="Verify official text / press release authenticity",
)
def verify_text_content(
    payload: VerifyTextRequest,
    db: Session = Depends(get_db),
) -> Any:
    """Verify raw text against the official government registry."""
    try:
        result = verify_text(db=db, text_content=payload.text)
        return result
    except Exception as e:
        logger.error("Text verification failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Text verification failed: {e}",
        )


@router.get(
    "/{verification_id}",
    response_model=VerificationResponse,
    summary="Retrieve past verification result by ID",
)
def get_verification(
    verification_id: str,
    db: Session = Depends(get_db),
) -> Any:
    """Retrieve historical verification proof bundle and confidence score."""
    result = get_verification_result(db=db, verification_id=verification_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Verification record not found: {verification_id}",
        )
    return result
