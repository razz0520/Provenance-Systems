"""Defensive Media and Upload Validation Utilities.

Validates file extensions, size limits, non-empty content, binary magic headers,
and cross-format signatures to prevent denial-of-service, decompression bombs,
and disguised malicious payloads from consuming server resources.
"""

import io
import logging
import os
from pathlib import Path
from typing import Optional, Set, Tuple, Union

from fastapi import UploadFile

from app.config import settings

logger = logging.getLogger(__name__)

# Permitted file extensions for official government verification
ALLOWED_EXTENSIONS: Set[str] = {
    # Images
    "jpg", "jpeg", "png", "webp", "gif", "bmp", "tiff", "tif",
    # Video
    "mp4", "avi", "mov", "mkv", "webm", "3gp",
    # Audio
    "mp3", "wav", "ogg", "flac", "m4a", "aac",
    # Documents
    "pdf",
    # Official Statements / Gazette text
    "txt", "json", "csv", "md",
}

# Image extensions
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif", "bmp", "tiff", "tif"}
VIDEO_EXTENSIONS = {"mp4", "avi", "mov", "mkv", "webm", "3gp"}
AUDIO_EXTENSIONS = {"mp3", "wav", "ogg", "flac", "m4a", "aac"}
DOC_EXTENSIONS = {"pdf"}
TEXT_EXTENSIONS = {"txt", "json", "csv", "md"}

# Known high-risk executable / script magic byte signatures (strictly rejected under any extension)
DANGEROUS_MAGIC_PREFIXES = [
    (b"MZ", "DOS / Windows PE executable (.exe/.dll)"),
    (b"\x7fELF", "Linux ELF executable"),
    (b"#!/", "Unix shell script"),
    (b"#!\x20", "Unix shell script"),
    (b"<?php", "PHP script"),
    (b"<script", "HTML/JavaScript script"),
    (b"PK\x03\x04\x14\x00\x08", "Compressed JAR / APK executable package"),
]


def _check_magic_bytes(ext: str, header: bytes) -> Tuple[bool, Optional[str]]:
    """
    Validate that the leading bytes do not contain dangerous executable signatures
    and do not cross-mismatch with contradictory file format signatures (e.g. PDF renamed to MP4,
    or PNG renamed to PDF).
    """
    if not header:
        return False, "File header is empty."

    # 1. Reject outright dangerous executable / script magic signatures disguised under allowed extensions
    for sig, desc in DANGEROUS_MAGIC_PREFIXES:
        if header.startswith(sig):
            return False, f"Dangerous file signature detected: {desc} is not permitted."

    # 2. PDF signature check and cross-mismatch check
    is_pdf_signature = header.startswith(b"%PDF-")
    if is_pdf_signature and ext not in DOC_EXTENSIONS:
        return False, f"Signature mismatch: PDF document uploaded with extension '.{ext}'."
    if ext == "pdf" and len(header) >= 5 and not is_pdf_signature and header.startswith(b"\x89PNG"):
        return False, "Signature mismatch: PNG image uploaded with extension '.pdf'."

    # 3. PNG signature check and cross-mismatch check
    is_png_signature = header.startswith(b"\x89PNG")
    if is_png_signature and ext not in IMAGE_EXTENSIONS:
        return False, f"Signature mismatch: PNG image uploaded with extension '.{ext}'."

    # 4. JPEG SOI marker check and cross-mismatch check
    is_jpeg_signature = header.startswith(b"\xff\xd8\xff")
    if is_jpeg_signature and ext not in IMAGE_EXTENSIONS:
        return False, f"Signature mismatch: JPEG image uploaded with extension '.{ext}'."

    # 5. GIF signature check and cross-mismatch check
    is_gif_signature = header.startswith(b"GIF87a") or header.startswith(b"GIF89a")
    if is_gif_signature and ext not in IMAGE_EXTENSIONS:
        return False, f"Signature mismatch: GIF image uploaded with extension '.{ext}'."

    # 6. Plain Text / JSON / CSV / MD: Ensure no binary null bytes
    if ext in TEXT_EXTENSIONS:
        if b"\x00" in header[:32]:
            return False, f"Invalid {ext.upper()}: binary content detected in text file."

    return True, None


def validate_file_payload(
    file_source: Union[UploadFile, str, Path, bytes, bytearray],
    filename: Optional[str] = None,
    max_size_bytes: Optional[int] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Validate an uploaded file payload through a layered defensive strategy:
    1. Non-empty check (> 0 bytes)
    2. Maximum file size check (<= MAX_UPLOAD_SIZE)
    3. Allowed extension check (strictly within permitted government media types)
    4. Magic-byte / binary header cross-validation to detect spoofed/disguised files.

    Returns:
        (is_valid: bool, error_message: Optional[str])
    """
    effective_max_size = max_size_bytes or settings.MAX_UPLOAD_SIZE
    fname = ""
    file_size = 0
    header_sample = b""

    try:
        if isinstance(file_source, UploadFile):
            fname = file_source.filename or filename or "content.bin"
            # Read first 32 bytes for header inspection, then seek back
            header_sample = file_source.file.read(32)
            file_source.file.seek(0, os.SEEK_END)
            file_size = file_source.file.tell()
            file_source.file.seek(0)
        elif isinstance(file_source, (bytes, bytearray)):
            fname = filename or "content.bin"
            file_size = len(file_source)
            header_sample = bytes(file_source[:32])
        elif isinstance(file_source, (str, Path)):
            path = Path(file_source)
            if not path.is_file():
                return False, f"File not found: {file_source}"
            fname = path.name
            file_size = path.stat().st_size
            with open(path, "rb") as f:
                header_sample = f.read(32)
        else:
            return False, f"Unsupported file payload type: {type(file_source)}"

        # 1. Non-empty check
        if file_size <= 0:
            return False, "Uploaded file is empty (0 bytes). Please provide valid content."

        # 2. Maximum file size check
        if file_size > effective_max_size:
            max_mb = effective_max_size // (1024 * 1024)
            actual_mb = round(file_size / (1024 * 1024), 2)
            return (
                False,
                f"File size ({actual_mb} MB) exceeds maximum allowed limit of {max_mb} MB.",
            )

        # 3. Extension check
        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        if not ext:
            return False, "Uploaded file missing file extension."
        if ext not in ALLOWED_EXTENSIONS:
            return (
                False,
                f"Unsupported file format '.{ext}'. Supported formats: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
            )

        # 4. Binary header / Magic-byte cross-validation
        is_magic_valid, magic_err = _check_magic_bytes(ext, header_sample)
        if not is_magic_valid:
            logger.warning("Magic byte validation rejected %s: %s", fname, magic_err)
            return False, magic_err

        return True, None

    except Exception as e:
        logger.error("File validation exception for %s: %s", fname, e)
        return False, f"File validation failed: {str(e)}"
