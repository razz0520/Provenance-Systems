"""Processing Timeout Protection Utilities.

Provides configurable execution timeouts for media extraction, OpenCV decoding,
FFmpeg operations, librosa acoustic analysis, and perceptual fingerprinting to prevent
pathological or corrupted files from hanging workers indefinitely.
"""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import logging
import time
from typing import Any, Callable, Dict, Optional, Tuple

from app.config import settings
from app.core.context import get_current_request_id

logger = logging.getLogger(__name__)


class ProcessingTimeoutError(Exception):
    """Raised when a media processing or verification operation exceeds the configured safety ceiling."""

    def __init__(self, message: Optional[str] = None, timeout_seconds: Optional[float] = None):
        self.timeout_seconds = timeout_seconds or float(getattr(settings, "MEDIA_PROCESSING_TIMEOUT_SECONDS", 120))
        msg = message or f"Media processing timed out after {self.timeout_seconds:.1f} seconds. Please provide a shorter or smaller file."
        super().__init__(msg)


def run_with_timeout(
    func: Callable[..., Any],
    args: Tuple[Any, ...] = (),
    kwargs: Optional[Dict[str, Any]] = None,
    timeout_seconds: Optional[float] = None,
    operation_name: str = "media_processing",
) -> Any:
    """
    Execute a synchronous media processing function within a bounded execution timeout.

    Note on Python Thread Safety:
        In CPython, worker threads running native C-extensions (like OpenCV or Librosa/Numpy)
        cannot be forcefully killed externally without terminating the host process.
        This function guarantees caller unblocking and safe HTTP/WhatsApp response generation
        upon reaching the timeout ceiling, while deterministic input bounds (10-minute video limit,
        120 frame cap, 2048px downscaling, and 50MP image cap) guarantee bounded execution of the
        underlying processing loop.

    Args:
        func: The callable to execute.
        args: Positional arguments for the callable.
        kwargs: Keyword arguments for the callable.
        timeout_seconds: Safety timeout in seconds (defaults to MEDIA_PROCESSING_TIMEOUT_SECONDS = 120).
        operation_name: Human-readable name of the operation for logging.

    Returns:
        The result of func(*args, **kwargs).

    Raises:
        ProcessingTimeoutError: If execution exceeds the timeout ceiling.
        Exception: Any exception raised by func.
    """
    effective_timeout = timeout_seconds or float(getattr(settings, "MEDIA_PROCESSING_TIMEOUT_SECONDS", 120))
    kwargs = kwargs or {}
    start_time = time.perf_counter()
    req_id = get_current_request_id() or "-"

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        try:
            result = future.result(timeout=effective_timeout)
            return result
        except FutureTimeoutError:
            elapsed = round(time.perf_counter() - start_time, 2)
            logger.warning(
                "[%s] Media operation '%s' TIMED OUT after %ss (limit: %ss).",
                req_id,
                operation_name,
                elapsed,
                effective_timeout,
            )
            raise ProcessingTimeoutError(
                message=f"Media processing timed out after {effective_timeout:.1f} seconds. Please try a shorter or smaller file.",
                timeout_seconds=effective_timeout,
            )
        except Exception as e:
            # Re-raise actual application exceptions
            raise e
