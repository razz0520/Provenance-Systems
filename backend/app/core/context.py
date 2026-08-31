"""Request Context and Correlation ID Management.

Provides thread-safe and async-safe request correlation ID propagation
using Python's contextvars.
"""

from contextvars import ContextVar
import logging
import re
from typing import Optional
import uuid

# Context variable storing the active request ID for the current async task / thread
request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)

# RFC 4122 UUID and safe alphanumeric format pattern (1-64 chars)
SAFE_REQUEST_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def get_current_request_id() -> str:
    """Retrieve the current request correlation ID, generating a new UUID if unset."""
    rid = request_id_ctx.get()
    if not rid:
        rid = str(uuid.uuid4())
        request_id_ctx.set(rid)
    return rid


def set_current_request_id(raw_id: Optional[str]) -> str:
    """
    Validate and set the request correlation ID in the context.
    If the supplied ID is missing, malformed, or oversized, a fresh UUID is generated.
    """
    if raw_id and isinstance(raw_id, str):
        cleaned = raw_id.strip()
        if SAFE_REQUEST_ID_REGEX.match(cleaned):
            request_id_ctx.set(cleaned)
            return cleaned

    fresh_id = str(uuid.uuid4())
    request_id_ctx.set(fresh_id)
    return fresh_id


class RequestIdFilter(logging.Filter):
    """Logging filter that injects the current request correlation ID into all log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get() or "-"
        return True
