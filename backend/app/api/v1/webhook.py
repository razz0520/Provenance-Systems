"""Webhook API endpoints for WhatsApp Cloud API integration."""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse

from app.database import SessionLocal
from app.services.whatsapp_service import handle_webhook, verify_webhook

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["Webhooks"])


def process_webhook_background(payload: Dict[str, Any]) -> None:
    """
    Background worker to asynchronously process WhatsApp webhook messages
    without blocking Meta's webhook delivery HTTP acknowledgment.
    """
    db = SessionLocal()
    try:
        handle_webhook(payload=payload, db=db)
    except Exception as e:
        logger.exception("Error in background WhatsApp webhook worker: %s", e)
    finally:
        db.close()


@router.get(
    "/whatsapp",
    summary="WhatsApp Webhook Verification (Meta Hub Challenge)",
    response_class=PlainTextResponse,
)
def whatsapp_webhook_verification(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
) -> PlainTextResponse:
    """
    Handle Meta's GET verification challenge for WhatsApp webhook registration.
    Meta sends:
    - hub.mode = 'subscribe'
    - hub.verify_token = '<WHATSAPP_VERIFY_TOKEN>'
    - hub.challenge = '<challenge_number>'
    """
    try:
        challenge = verify_webhook(
            mode=hub_mode,
            token=hub_verify_token,
            challenge=hub_challenge,
        )
        return PlainTextResponse(content=challenge, status_code=status.HTTP_200_OK)
    except ValueError as e:
        logger.warning("WhatsApp verification challenge failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verification token mismatch or invalid mode.",
        )


@router.post(
    "/whatsapp",
    summary="Receive WhatsApp Webhook Events (Messages, Media, Status Updates)",
)
async def whatsapp_webhook_event(
    request: Request,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    """
    Receive incoming messages and events from Meta WhatsApp Cloud API.
    Immediately returns 200 OK to Meta and executes message verification
    asynchronously in the background task worker.
    """
    try:
        payload = await request.json()
    except Exception as e:
        logger.error("Failed to parse WhatsApp webhook JSON payload: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload.",
        )

    # Dispatch to background task worker for non-blocking asynchronous processing
    background_tasks.add_task(process_webhook_background, payload)
    return {"status": "EVENT_RECEIVED"}
