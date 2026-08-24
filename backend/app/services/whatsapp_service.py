"""WhatsApp Integration Service for Citizen Provenance Verification.

Handles:
1. Meta Cloud API Webhook verification (GET challenge).
2. Incoming message parsing and event dispatch (text, media).
3. Sender-level rate limiting using Redis.
4. Message deduplication and verification caching via Redis.
5. Media downloading, validation, and temporary file management.
6. Execution of cryptographic and perceptual provenance verification.
7. Exponential backoff retry logic for transient Meta Graph API calls.
8. Formatted WhatsApp response message templating and delivery via Meta Graph API.
"""

from datetime import datetime, timezone
import hashlib
import json
import logging
import mimetypes
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import uuid

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.core.hash_service import calculate_bytes_hash, calculate_file_hash
from app.core.security import check_rate_limit, get_redis_client, increment_rate_counter
from app.models.database import VerificationVerdict
from app.services.verification_service import (
    get_verification_result,
    verify_file,
    verify_text,
)

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v18.0"
GRAPH_API_BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# MIME Type to File Extension Mapping
MIME_EXTENSION_MAP = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "video/x-msvideo": "avi",
    "video/webm": "webm",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/ogg": "ogg",
    "audio/aac": "aac",
    "audio/m4a": "m4a",
    "audio/mp4": "m4a",
    "application/pdf": "pdf",
    "text/plain": "txt",
}

# Maximum messages processed per webhook batch
MAX_BATCH_MESSAGES = 20

# In-memory deduplication fallback
_in_memory_seen_messages: Dict[str, datetime] = {}


def execute_with_retry(
    request_func: Callable[[], httpx.Response],
    max_retries: int = 3,
    base_delay: float = 0.5,
    description: str = "Meta Graph API Request",
) -> Optional[httpx.Response]:
    """
    Execute an HTTP request with exponential backoff for transient failures.

    Retries on:
    - Connection timeouts, network errors, connection aborts
    - HTTP 5xx Server errors (500, 502, 503, 504)

    Does NOT retry:
    - HTTP 4xx Client errors (400, 401, 403, 404, etc.)
    """
    last_response: Optional[httpx.Response] = None
    for attempt in range(max_retries):
        try:
            response = request_func()
            # 2xx Success or 4xx Client Error: Return immediately (no retry)
            if response.status_code < 500:
                return response

            logger.warning(
                "Transient 5xx error during %s (attempt %d/%d, status %d). Retrying...",
                description,
                attempt + 1,
                max_retries,
                response.status_code,
            )
            last_response = response
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as e:
            logger.warning(
                "Transient network error during %s (attempt %d/%d: %s). Retrying...",
                description,
                attempt + 1,
                max_retries,
                e,
            )
        except Exception as e:
            logger.error("Non-retryable exception during %s: %s", description, e)
            return None

        if attempt < max_retries - 1:
            delay = base_delay * (2 ** attempt)
            time.sleep(delay)

    return last_response


class WhatsAppService:
    """Enterprise service for WhatsApp Cloud API verification and messaging."""

    # ========================================================================
    # 1. Webhook Handler & Routing
    # ========================================================================

    @classmethod
    def verify_webhook(
        cls,
        mode: Optional[str],
        token: Optional[str],
        challenge: Optional[str],
    ) -> str:
        """
        Verify the webhook challenge from Meta.

        Args:
            mode: hub.mode parameter (should be 'subscribe').
            token: hub.verify_token parameter.
            challenge: hub.challenge parameter.

        Returns:
            The challenge string if verification succeeds.

        Raises:
            ValueError: If mode or token is invalid.
        """
        expected_token = settings.WHATSAPP_VERIFY_TOKEN
        if mode == "subscribe" and token == expected_token:
            logger.info("WhatsApp webhook challenge verification succeeded.")
            return str(challenge) if challenge else ""

        logger.warning(
            "WhatsApp webhook verification failed. Received mode=%s, token=%s",
            mode,
            token,
        )
        raise ValueError("Invalid verification token or mode")

    @classmethod
    def is_duplicate_message(cls, msg_id: Optional[str]) -> bool:
        """Check and mark WhatsApp message ID to prevent duplicate processing."""
        if not msg_id:
            return False

        r = get_redis_client()
        key = f"wa_msg_seen:{msg_id}"
        if r:
            try:
                # Set if not exists with 24-hour TTL
                was_set = r.set(key, "1", nx=True, ex=86400)
                return not bool(was_set)
            except Exception:
                pass

        # In-memory fallback
        now = datetime.now(timezone.utc)
        if msg_id in _in_memory_seen_messages:
            return True
        _in_memory_seen_messages[msg_id] = now
        return False

    @classmethod
    def get_cached_verification(cls, cache_key: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached verification result from Redis."""
        r = get_redis_client()
        if r:
            try:
                val = r.get(f"wa_verif_cache:{cache_key}")
                if val:
                    return json.loads(val)
            except Exception as e:
                logger.debug("Redis verification cache get error: %s", e)
        return None

    @classmethod
    def set_cached_verification(
        cls,
        cache_key: str,
        result: Dict[str, Any],
        ttl_seconds: int = 3600,
    ) -> None:
        """Store verification result in Redis cache with TTL (1 hour)."""
        r = get_redis_client()
        if r:
            try:
                r.setex(f"wa_verif_cache:{cache_key}", ttl_seconds, json.dumps(result))
            except Exception as e:
                logger.debug("Redis verification cache set error: %s", e)

    @classmethod
    def handle_webhook(
        cls,
        payload: Dict[str, Any],
        db: Session,
    ) -> Dict[str, Any]:
        """
        Main entry point for handling incoming Meta webhook notifications.

        Parses incoming payload, extracts messages, applies batch limits,
        dispatches processing, and sends responses back to the sender.
        """
        processed_count = 0
        results: List[Dict[str, Any]] = []

        entries = payload.get("entry", [])
        if not entries:
            logger.debug("Received webhook with no entries.")
            return {"status": "ignored", "reason": "no_entries"}

        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})

                # Check for delivery/read statuses (ignore for processing)
                if "statuses" in value and "messages" not in value:
                    logger.debug("Received message delivery status update.")
                    continue

                messages = value.get("messages", [])
                contacts = {c.get("wa_id"): c.get("profile", {}).get("name") for c in value.get("contacts", [])}

                for message in messages:
                    if processed_count >= MAX_BATCH_MESSAGES:
                        logger.warning("Reached maximum batch messages cap (%d).", MAX_BATCH_MESSAGES)
                        break

                    sender_id = message.get("from")
                    sender_name = contacts.get(sender_id, "Citizen")

                    try:
                        res = cls.process_message(message=message, sender_name=sender_name, db=db)
                        results.append(res)
                        processed_count += 1
                    except Exception as e:
                        logger.exception("Error processing WhatsApp message %s: %s", message.get("id"), e)
                        if sender_id:
                            cls.send_whatsapp_message(
                                to_number=sender_id,
                                message_text=cls.format_invalid_response(
                                    "An unexpected error occurred while processing your request. Please try again."
                                ),
                            )

        return {
            "status": "success",
            "processed_count": processed_count,
            "results": results,
        }

    @classmethod
    def process_message(
        cls,
        message: Dict[str, Any],
        sender_name: str,
        db: Session,
    ) -> Dict[str, Any]:
        """
        Process an individual WhatsApp message (text, media, interactive).
        Applies per-user rate limiting, deduplication, and caching.
        """
        msg_type = message.get("type", "unknown")
        from_number = message.get("from")
        msg_id = message.get("id")

        if not from_number:
            return {"error": "missing_sender"}

        logger.info("Processing WhatsApp message [ID: %s, Type: %s] from %s", msg_id, msg_type, from_number)

        # 1. Message Deduplication Check
        if msg_id and cls.is_duplicate_message(msg_id):
            logger.info("Skipping duplicate WhatsApp message ID: %s", msg_id)
            return {"type": "duplicate_skipped", "msg_id": msg_id}

        # 2. Mark message as read
        if msg_id:
            cls.mark_message_as_read(msg_id)

        # 3. Per-user WhatsApp Rate Limiting (10 requests per 60 seconds per phone number)
        rate_key = f"wa_user_rate:{from_number}"
        request_count = increment_rate_counter(rate_key, window_seconds=60)
        if request_count > 10:
            logger.warning("WhatsApp rate limit exceeded for sender: %s (count: %d)", from_number, request_count)
            cls.send_whatsapp_message(
                to_number=from_number,
                message_text=cls.format_rate_limit_response(),
            )
            return {"type": "rate_limited", "recipient": from_number}

        # 4. Text Message Processing
        if msg_type == "text":
            text_body = message.get("text", {}).get("body", "").strip()

            # Help / Greeting Keywords
            if text_body.lower() in ["hi", "hello", "hey", "help", "info", "start", "menu", "verify"]:
                help_payload = cls.format_help_response(sender_name=sender_name)
                cls.send_interactive_message(
                    to_number=from_number,
                    body_text=help_payload["body_text"],
                    buttons=help_payload["buttons"],
                )
                return {"type": "help", "recipient": from_number}

            # Verification of press release or text statement (with Redis caching)
            try:
                text_hash = calculate_bytes_hash(text_body.encode("utf-8"))
                cache_key = f"text:{text_hash}"
                cached_res = cls.get_cached_verification(cache_key)

                if cached_res:
                    logger.info("Serving text verification from cache for hash %s", text_hash)
                    verif_result = cached_res
                else:
                    verif_result = verify_text(db=db, text_content=text_body)
                    cls.set_cached_verification(cache_key, verif_result)

                verdict_payload = cls.format_verification_result(verif_result)
                cls.send_interactive_message(
                    to_number=from_number,
                    body_text=verdict_payload["body_text"],
                    buttons=verdict_payload["buttons"],
                )
                return {
                    "type": "text_verification",
                    "verification_id": verif_result.get("verification_id"),
                    "verdict": verif_result.get("verdict"),
                }
            except Exception as e:
                logger.error("Text verification failed for WhatsApp: %s", e)
                cls.send_whatsapp_message(
                    to_number=from_number,
                    message_text="⚠️ We couldn't verify that text statement. Please try again.",
                )
                return {"error": str(e)}

        # 5. Media Messages (image, video, audio, voice, document)
        elif msg_type in ["image", "video", "audio", "voice", "document"]:
            media_data = message.get(msg_type, {})
            media_id = media_data.get("id")
            mime_type = media_data.get("mime_type")
            filename = media_data.get("filename")

            if not media_id:
                cls.send_whatsapp_message(
                    to_number=from_number,
                    message_text="⚠️ Could not read attached media file identifier.",
                )
                return {"error": "missing_media_id"}

            # Notify user that analysis is in progress
            cls.send_whatsapp_message(
                to_number=from_number,
                message_text="🔍 *Analyzing content provenance & cryptographic ledger...*\nPlease wait a moment.",
            )

            res = cls.handle_media_message(
                media_id=media_id,
                media_type=msg_type,
                mime_type=mime_type,
                filename=filename,
                db=db,
            )

            if res.get("success"):
                verdict_payload = cls.format_verification_result(res["verification_result"])
                cls.send_interactive_message(
                    to_number=from_number,
                    body_text=verdict_payload["body_text"],
                    buttons=verdict_payload["buttons"],
                )
            else:
                error_msg = res.get("error", "Could not verify media file.")
                cls.send_whatsapp_message(to_number=from_number, message_text=f"⚠️ {error_msg}")

            return res

        # 6. Interactive Button Replies
        elif msg_type == "interactive":
            button_reply = message.get("interactive", {}).get("button_reply", {})
            button_id = button_reply.get("id", "")

            if button_id.startswith("btn_proof"):
                parts = button_id.split(":", 1)
                verification_id = parts[1] if len(parts) > 1 else None
                proof_result = get_verification_result(db, verification_id) if verification_id else None
                proof_text = cls.format_proof_message(proof_result)
                cls.send_whatsapp_message(to_number=from_number, message_text=proof_text)
                return {"type": "proof_sent", "recipient": from_number}

            elif button_id == "btn_report":
                report_text = (
                    "📝 *Report this content officially*\n\n"
                    "Our system does not handle government complaints directly. Please use "
                    "the official PIB Fact Check Portal to submit this content for investigation.\n\n"
                    "🔗 https://factcheck.pib.gov.in/"
                )
                cls.send_whatsapp_message(to_number=from_number, message_text=report_text)
                return {"type": "report_redirect", "recipient": from_number}

            elif button_id == "btn_explainer":
                cls.send_whatsapp_message(
                    to_number=from_number,
                    message_text=cls.format_explainer_message(),
                )
                return {"type": "explainer_sent", "recipient": from_number}

            else:
                cls.send_whatsapp_message(
                    to_number=from_number,
                    message_text="Please send an image, video, audio clip, or text to verify.",
                )
                return {"type": "unknown_button", "button_id": button_id}

        # 7. Unsupported Type
        else:
            reply_text = (
                f"⚠️ *Unsupported message type:* `{msg_type}`\n\n"
                "Please send an *image*, *video*, *audio clip*, *PDF document*, or *official text statement* to verify."
            )
            cls.send_whatsapp_message(to_number=from_number, message_text=reply_text)
            return {"type": "unsupported", "msg_type": msg_type}

    @classmethod
    def handle_media_message(
        cls,
        media_id: str,
        media_type: str,
        mime_type: Optional[str] = None,
        filename: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """Download media from Meta, validate, verify (with caching), and clean up."""
        temp_file_path: Optional[str] = None
        try:
            # Step 1: Download media with retry logic
            temp_file_path = cls.download_media(media_id=media_id, mime_type=mime_type)
            if not temp_file_path:
                return {"success": False, "error": "Failed to download media from WhatsApp servers."}

            # Step 2: Validate downloaded file
            if not cls.validate_media_file(temp_file_path):
                return {"success": False, "error": "Media file exceeds size limit (16MB) or has an invalid format."}

            # Step 3: Check cache by media SHA-256
            media_sha256 = calculate_file_hash(temp_file_path)
            cache_key = f"media:{media_sha256}"
            cached_res = cls.get_cached_verification(cache_key)

            if cached_res:
                logger.info("Serving media verification from cache for SHA-256 %s", media_sha256)
                verif_result = cached_res
            else:
                # Step 4: Process through complete provenance verification pipeline
                verif_result = cls.process_through_verification(
                    file_path=temp_file_path,
                    db=db,
                    filename=filename or Path(temp_file_path).name,
                )
                cls.set_cached_verification(cache_key, verif_result)

            return {
                "success": True,
                "verification_result": verif_result,
            }

        except Exception as e:
            logger.exception("Media verification handling error: %s", e)
            return {"success": False, "error": str(e)}
        finally:
            # Step 5: Guaranteed cleanup of temporary files
            if temp_file_path:
                cls.cleanup_temp_files(temp_file_path)

    # ========================================================================
    # 2. Media Processing & Meta API Client (with Exponential Backoff)
    # ========================================================================

    @classmethod
    def download_media(
        cls,
        media_id: str,
        mime_type: Optional[str] = None,
    ) -> Optional[str]:
        """Download media from Meta Graph API using exponential backoff retry for transient errors."""
        access_token = settings.WHATSAPP_ACCESS_TOKEN
        if not access_token:
            logger.error("WHATSAPP_ACCESS_TOKEN is not configured.")
            return None

        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            # 1. Fetch Media Metadata URL with retry
            meta_url = f"{GRAPH_API_BASE_URL}/{media_id}"
            with httpx.Client(timeout=20.0) as client:
                res = execute_with_retry(
                    lambda: client.get(meta_url, headers=headers),
                    max_retries=3,
                    base_delay=0.5,
                    description=f"Meta Media Metadata [ID: {media_id}]",
                )

                if not res or res.status_code != 200:
                    logger.error("Failed to fetch media metadata for %s", media_id)
                    return None

                media_info = res.json()
                download_url = media_info.get("url")
                detected_mime = media_info.get("mime_type") or mime_type or "application/octet-stream"

                if not download_url:
                    logger.error("No download URL in WhatsApp media metadata: %s", media_info)
                    return None

                # Determine extension
                clean_mime = detected_mime.split(";")[0].strip().lower()
                ext = MIME_EXTENSION_MAP.get(clean_mime)
                if not ext:
                    ext = mimetypes.guess_extension(clean_mime) or ".bin"
                ext = ext.lstrip(".")

                # 2. Download Media Content Binary with retry
                dl_res = execute_with_retry(
                    lambda: client.get(download_url, headers=headers),
                    max_retries=3,
                    base_delay=0.5,
                    description=f"Meta Media Download [ID: {media_id}]",
                )

                if not dl_res or dl_res.status_code != 200:
                    logger.error("Failed to download media binary payload for %s", media_id)
                    return None

                # 3. Save to temporary directory
                temp_dir = Path(settings.TEMP_DIR)
                temp_dir.mkdir(parents=True, exist_ok=True)

                temp_file = tempfile.NamedTemporaryFile(
                    dir=str(temp_dir),
                    suffix=f".{ext}",
                    delete=False,
                )
                temp_file.write(dl_res.content)
                temp_file.close()

                logger.info("Successfully downloaded WhatsApp media [ID: %s] to %s", media_id, temp_file.name)
                return temp_file.name

        except Exception as e:
            logger.exception("Exception downloading WhatsApp media %s: %s", media_id, e)
            return None

    @classmethod
    def validate_media_file(cls, file_path: str) -> bool:
        """Validate media file exists, is non-empty, and respects size limits."""
        if not file_path or not os.path.exists(file_path):
            return False

        try:
            file_size = os.path.getsize(file_path)
            if file_size <= 0:
                logger.warning("Media file is empty: %s", file_path)
                return False
            if file_size > settings.MAX_UPLOAD_SIZE:
                logger.warning("Media file size %d exceeds limit %d", file_size, settings.MAX_UPLOAD_SIZE)
                return False
            return True
        except Exception as e:
            logger.error("Error validating media file %s: %s", file_path, e)
            return False

    @classmethod
    def process_through_verification(
        cls,
        file_path: str,
        db: Session,
        filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run the file through the complete provenance verification pipeline."""
        return verify_file(db=db, upload_file=file_path, filename=filename)

    @classmethod
    def cleanup_temp_files(cls, file_path: Optional[str]) -> None:
        """Safely delete temporary files created during processing."""
        if file_path and os.path.exists(file_path):
            try:
                os.unlink(file_path)
                logger.debug("Cleaned up temporary file: %s", file_path)
            except Exception as e:
                logger.warning("Failed to delete temporary file %s: %s", file_path, e)

    # ========================================================================
    # 3. Response Formatting & Message Templates
    # ========================================================================

    @classmethod
    def format_verification_result(cls, result: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch result formatting based on verdict. Returns interactive payload."""
        verdict = result.get("verdict", "")
        evidence = result.get("evidence_bundle", {})
        matched_content = result.get("matched_content") or {}
        verification_id = result.get("verification_id", "")

        # Merge matched content fields for richer display
        merged_evidence = dict(evidence)
        if matched_content:
            merged_evidence["original_filename"] = matched_content.get("original_filename")
            merged_evidence["content_type"] = matched_content.get("content_type")

        if verdict == VerificationVerdict.VERIFIED.value:
            payload = cls.format_verified_response(merged_evidence)
        elif verdict == VerificationVerdict.SUSPICIOUS.value:
            payload = cls.format_suspicious_response(merged_evidence)
        elif verdict == VerificationVerdict.PROVEN_INVALID.value:
            payload = cls.format_invalid_response()
        else:
            payload = cls.format_unsigned_response()

        # Attach verification_id to proof button for targeted retrieval
        if verification_id:
            for btn in payload.get("buttons", []):
                if btn.get("id") == "btn_proof":
                    btn["id"] = f"btn_proof:{verification_id}"

        return payload

    @classmethod
    def format_verified_response(
        cls,
        evidence: Dict[str, Any],
        confidence: float = 1.0,
    ) -> Dict[str, Any]:
        """Format official VERIFIED response as interactive message payload."""
        publisher = (
            evidence.get("publisher_organization")
            or evidence.get("publisher_name")
            or "Official Government Authority"
        )

        content_type_raw = str(evidence.get("content_type", "")).lower()
        type_labels = {
            "image": "image",
            "video": "video",
            "audio": "audio",
            "document": "document",
            "text": "statement",
        }
        type_label = type_labels.get(content_type_raw, "document")

        manifest = evidence.get("manifest_data") or {}
        raw_ts = manifest.get("timestamp") or evidence.get("created_at")
        formatted_date = "recently"
        if raw_ts:
            try:
                dt = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
                formatted_date = dt.strftime("%d %b %Y")
            except Exception:
                formatted_date = str(raw_ts)[:10]

        body_text = (
            f"✅ *Verified official content* — this {type_label} matches an official "
            f"release from *{publisher}*, published {formatted_date}. "
            f"It has not been edited or manipulated."
        )

        return {
            "body_text": body_text,
            "buttons": [
                {"id": "btn_proof", "title": "How was this checked"},
            ],
        }

    @classmethod
    def format_suspicious_response(
        cls,
        evidence: Dict[str, Any],
        confidence: float = 0.0,
    ) -> Dict[str, Any]:
        """Format SUSPICIOUS / Altered Content response as interactive message payload."""
        publisher = (
            evidence.get("publisher_organization")
            or evidence.get("publisher_name")
            or "Official Government Source"
        )

        body_text = (
            f"⚠️ *This appears to be a modified version* of official content from *{publisher}*. "
            f"Parts may have been altered or taken out of context."
        )

        return {
            "body_text": body_text,
            "buttons": [
                {"id": "btn_proof", "title": "How was this checked"},
                {"id": "btn_report", "title": "Report this content"},
            ],
        }

    @classmethod
    def format_unsigned_response(cls) -> Dict[str, Any]:
        """Format UNSIGNED response as interactive message payload."""
        body_text = (
            "❓ *We can't confirm this is official government content* — it isn't in our "
            "verified records. This doesn't necessarily mean it's fake, only that no "
            "government publisher has registered it."
        )

        return {
            "body_text": body_text,
            "buttons": [
                {"id": "btn_proof", "title": "How was this checked"},
                {"id": "btn_report", "title": "Report this content"},
            ],
        }

    @classmethod
    def format_invalid_response(cls, reason: str = "Invalid content or corrupted file.") -> Dict[str, Any]:
        """Format INVALID response as interactive message payload."""
        body_text = (
            "🚫 *This does not match any official record* and shows signs of tampering. "
            "Treat this content with caution."
        )

        return {
            "body_text": body_text,
            "buttons": [
                {"id": "btn_proof", "title": "How was this checked"},
                {"id": "btn_report", "title": "Report this content"},
            ],
        }

    @classmethod
    def format_rate_limit_response(cls) -> str:
        """Format Rate Limit warning response as concise plain text."""
        return (
            "⏳ *Rate Limit Exceeded*\n\n"
            "You have submitted too many requests in a short period.\n"
            "Please wait a minute before submitting additional media or statements for verification."
        )

    @classmethod
    def format_help_response(cls, sender_name: str = "Citizen") -> Dict[str, Any]:
        """Format Greeting / Onboarding Menu with interactive button."""
        body_text = (
            f"👋 *Welcome {sender_name}!*\n\n"
            "This number checks if media or text is official government content.\n\n"
            "*How to verify:*\n"
            "1️⃣ Forward an image, video, or audio clip\n"
            "2️⃣ Paste a text statement or press release\n"
            "3️⃣ Get your result in seconds"
        )
        return {
            "body_text": body_text,
            "buttons": [
                {"id": "btn_explainer", "title": "What is verified?"},
            ],
        }

    @classmethod
    def format_proof_message(cls, result: Optional[Dict[str, Any]]) -> str:
        """Format proof-on-tap message showing only signals actually present in the result."""
        if not result:
            return (
                "ℹ️ Verification proof details are unavailable.\n"
                "Please submit the media or statement to verify again."
            )

        evidence = result.get("evidence_bundle") or {}
        verdict = result.get("verdict", "")
        lines: List[str] = ["*How this was checked:*", ""]

        # 1. SHA-256 hash match
        if evidence.get("sha256_match") is True:
            lines.append("• Matches the original file — exact match")
            lines.append("  _Technical: SHA-256 hash match confirmed_")
            lines.append("")
        elif evidence.get("match_type") == "PERCEPTUAL_SIMILARITY":
            lines.append("• File content differs from the original — not an exact copy")
            lines.append("  _Technical: SHA-256 hash mismatch (altered or re-encoded)_")
            lines.append("")

        # 2. Perceptual fingerprint match
        perceptual_status = evidence.get("perceptual_match_status", "")
        if perceptual_status == "EXACT_MATCH":
            lines.append("• Looks and sounds like the original — exact match")
            lines.append("  _Technical: Perceptual fingerprint (pHash/dHash) exact match_")
            lines.append("")
        elif perceptual_status == "SIMILAR_MATCH":
            sim = evidence.get("perceptual_similarity_score") or evidence.get("similarity_score", 0)
            lines.append(f"• Looks and sounds like the original — {int(sim)}% match")
            lines.append(f"  _Technical: Perceptual fingerprint similarity {sim}%_")
            lines.append("")

        # 3. Ed25519 digital signature
        if evidence.get("digital_signature") is not None:
            if evidence.get("signature_valid") is True:
                lines.append("• Digitally signed by the publisher — valid")
                lines.append("  _Technical: Ed25519 cryptographic signature verified_")
            else:
                lines.append("• Digital signature check — failed")
                lines.append("  _Technical: Ed25519 digital signature invalid or broken_")
            lines.append("")

        # 4. C2PA provenance manifest
        if evidence.get("manifest_data") is not None:
            if evidence.get("manifest_valid") is True:
                lines.append("• Official provenance record — valid")
                lines.append("  _Technical: C2PA-standard provenance manifest authenticated_")
            else:
                lines.append("• Provenance record check — failed")
                lines.append("  _Technical: C2PA provenance manifest validation failed_")
            lines.append("")

        # 5. Hash-chain ledger anchoring
        if evidence.get("chain_block_id") is not None:
            block_id = evidence.get("chain_block_id")
            if evidence.get("chain_integrity") is True:
                lines.append("• Recorded on tamper-proof ledger — confirmed")
                lines.append(f"  _Technical: Hash-chain ledger block #{block_id} integrity confirmed_")
            else:
                lines.append("• Ledger record check — failed")
                lines.append(f"  _Technical: Hash-chain ledger block #{block_id} integrity could not be confirmed_")
            lines.append("")

        # Fallback if no individual signals were present
        if len(lines) <= 2:
            if verdict == VerificationVerdict.UNSIGNED.value or verdict == "UNSIGNED":
                lines.append("• Registry check — no matching records found")
                lines.append("  _Technical: No SHA-256, fingerprint, or signature match in registry_")
            elif verdict == VerificationVerdict.PROVEN_INVALID.value or verdict == "PROVEN_INVALID":
                lines.append("• Authenticity check — failed")
                lines.append("  _Technical: Cryptographic signature or manifest validation failed_")
            else:
                notice = evidence.get("notice", "")
                if notice:
                    lines.append(f"_{notice}_")
                else:
                    lines.append("_No detailed verification signals available._")

        return "\n".join(lines).strip()

    @classmethod
    def format_explainer_message(cls) -> str:
        """Full technical explainer sent on tap of 'What is verified?' button."""
        lines = [
            "*What does 'verified' mean?*",
            "",
            "When an official authority releases content, our system creates a tamper-proof digital record using 5 security mechanisms:",
            "",
            "*1. Cryptographic File Fingerprint (SHA-256)*",
            "A unique mathematical hash of the file. Even a 1-pixel or 1-byte change creates a completely different hash.",
            "",
            "*2. Acoustic & Visual Fingerprint (pHash/dHash/MFCC)*",
            "A perceptual fingerprint that identifies the underlying image, video, or audio even across compression and resizing.",
            "",
            "*3. Authorized Digital Signature (Ed25519)*",
            "Signed using the publisher's private key. Verifies authenticity and non-repudiation.",
            "",
            "*4. C2PA Provenance Manifest*",
            "An open-standard manifest detailing authorship, timestamps, and editing history.",
            "",
            "*5. Immutable Hash-Chain Ledger*",
            "Every publication is permanently anchored into a tamper-evident cryptographic hash chain.",
        ]
        return "\n".join(lines)

    # ========================================================================
    # 4. WhatsApp Cloud API Messaging Dispatch (with Retry)
    # ========================================================================

    @classmethod
    def send_whatsapp_message(
        cls,
        to_number: str,
        message_text: str,
    ) -> bool:
        """Send a text message via Meta WhatsApp Cloud API with retry logic."""
        phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        access_token = settings.WHATSAPP_ACCESS_TOKEN

        if not phone_number_id or not access_token:
            logger.warning(
                "WhatsApp credentials not configured. Simulating dispatch to %s:\n%s",
                to_number,
                message_text,
            )
            return True

        url = f"{GRAPH_API_BASE_URL}/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_number,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": message_text,
            },
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                res = execute_with_retry(
                    lambda: client.post(url, headers=headers, json=payload),
                    max_retries=3,
                    base_delay=0.5,
                    description=f"WhatsApp Send to {to_number}",
                )

                if res and res.status_code in [200, 201]:
                    logger.info("Successfully sent WhatsApp message to %s (Status: %d)", to_number, res.status_code)
                    return True
                else:
                    status_c = res.status_code if res else "None"
                    logger.error("WhatsApp send failed (Status %s)", status_c)
                    return False
        except Exception as e:
            logger.exception("Exception sending WhatsApp message to %s: %s", to_number, e)
            return False

    @classmethod
    def send_interactive_message(
        cls,
        to_number: str,
        body_text: str,
        buttons: List[Dict[str, str]],
    ) -> bool:
        """Send an interactive reply-button message via Meta WhatsApp Cloud API."""
        phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        access_token = settings.WHATSAPP_ACCESS_TOKEN

        api_buttons = []
        for btn in buttons[:3]:
            api_buttons.append({
                "type": "reply",
                "reply": {
                    "id": btn["id"],
                    "title": btn["title"][:20],
                },
            })

        if not phone_number_id or not access_token:
            logger.warning(
                "WhatsApp credentials not configured. Simulating interactive dispatch to %s:\n%s\nButtons: %s",
                to_number,
                body_text,
                [b["title"] for b in buttons],
            )
            return True

        url = f"{GRAPH_API_BASE_URL}/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body_text},
                "action": {
                    "buttons": api_buttons,
                },
            },
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                res = execute_with_retry(
                    lambda: client.post(url, headers=headers, json=payload),
                    max_retries=3,
                    base_delay=0.5,
                    description=f"WhatsApp Interactive Send to {to_number}",
                )

                if res and res.status_code in [200, 201]:
                    logger.info("Successfully sent WhatsApp interactive message to %s (Status: %d)", to_number, res.status_code)
                    return True
                else:
                    status_c = res.status_code if res else "None"
                    logger.error("WhatsApp interactive send failed (Status %s)", status_c)
                    return False
        except Exception as e:
            logger.exception("Exception sending WhatsApp interactive message to %s: %s", to_number, e)
            return False

    @classmethod
    def mark_message_as_read(cls, message_id: str) -> bool:
        """Mark incoming WhatsApp message as read."""
        phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        access_token = settings.WHATSAPP_ACCESS_TOKEN

        if not phone_number_id or not access_token:
            return True

        url = f"{GRAPH_API_BASE_URL}/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }

        try:
            with httpx.Client(timeout=5.0) as client:
                res = execute_with_retry(
                    lambda: client.post(url, headers=headers, json=payload),
                    max_retries=2,
                    base_delay=0.5,
                    description=f"Mark Read [ID: {message_id}]",
                )
                return bool(res and res.status_code in [200, 201])
        except Exception as e:
            logger.debug("Failed to mark message %s as read: %s", message_id, e)
            return False


# Functional aliases for direct export
verify_webhook = WhatsAppService.verify_webhook
handle_webhook = WhatsAppService.handle_webhook
process_message = WhatsAppService.process_message
handle_media_message = WhatsAppService.handle_media_message
download_media = WhatsAppService.download_media
validate_media_file = WhatsAppService.validate_media_file
process_through_verification = WhatsAppService.process_through_verification
cleanup_temp_files = WhatsAppService.cleanup_temp_files
format_verification_result = WhatsAppService.format_verification_result
format_verified_response = WhatsAppService.format_verified_response
format_suspicious_response = WhatsAppService.format_suspicious_response
format_unsigned_response = WhatsAppService.format_unsigned_response
format_invalid_response = WhatsAppService.format_invalid_response
format_rate_limit_response = WhatsAppService.format_rate_limit_response
format_help_response = WhatsAppService.format_help_response
format_proof_message = WhatsAppService.format_proof_message
format_explainer_message = WhatsAppService.format_explainer_message
send_whatsapp_message = WhatsAppService.send_whatsapp_message
send_interactive_message = WhatsAppService.send_interactive_message


