"""Test Data Generators and Helper Utilities for Provenance Test Suites."""

import io
import math
import struct
import uuid
from PIL import Image, ImageDraw


def generate_sample_image(text: str = "OFFICIAL GOVERNMENT COMMUNIQUE", size: tuple = (300, 300)) -> bytes:
    """Generate a valid PNG image representing an authentic government release."""
    img = Image.new("RGB", size, color=(245, 248, 252))
    draw = ImageDraw.Draw(img)
    # Border
    draw.rectangle([10, 10, size[0] - 10, size[1] - 10], outline=(20, 50, 90), width=4)
    # Emblem placeholder
    draw.ellipse([size[0] // 2 - 30, 30, size[0] // 2 + 30, 90], fill=(218, 165, 32), outline=(139, 69, 19), width=2)
    # Text
    draw.text((25, size[1] // 2), text, fill=(10, 25, 47))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def generate_compressed_image(original_png_bytes: bytes, quality: int = 75) -> bytes:
    """Generate a re-compressed JPEG version of an image (simulating social media forwarding)."""
    img = Image.open(io.BytesIO(original_png_bytes))
    buffer = io.BytesIO()
    img.convert("RGB").save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def generate_modified_image(original_png_bytes: bytes, alteration_text: str = "ALTERED / FAKE NOTICE") -> bytes:
    """Generate an altered/tampered version of an original image."""
    img = Image.open(io.BytesIO(original_png_bytes)).convert("RGB")
    draw = ImageDraw.Draw(img)
    # Draw a big red tampering overlay banner
    w, h = img.size
    draw.rectangle([0, h - 80, w, h], fill=(220, 38, 38))
    draw.text((20, h - 50), alteration_text, fill=(255, 255, 255))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def generate_distinct_image(size: tuple = (300, 300)) -> bytes:
    """Generate a completely distinct, unregistered image for negative tests."""
    img = Image.new("RGB", size, color=(160, 20, 60))
    draw = ImageDraw.Draw(img)
    draw.ellipse([30, 30, size[0] - 30, size[1] - 30], fill=(255, 215, 0), outline=(0, 0, 0), width=4)
    draw.text((40, size[1] // 2), "UNREGISTERED INDEPENDENT MEDIA", fill=(0, 0, 0))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def generate_sample_audio(duration_sec: float = 1.5, sample_rate: int = 16000, freq: float = 440.0) -> bytes:
    """Generate a synthetic 16-bit PCM WAV audio file with a pure sine wave tone."""
    num_samples = int(duration_sec * sample_rate)
    buffer = io.BytesIO()

    # RIFF header
    buffer.write(b"RIFF")
    buffer.write(struct.pack("<I", 36 + num_samples * 2))
    buffer.write(b"WAVE")
    # fmt subchunk
    buffer.write(b"fmt ")
    buffer.write(struct.pack("<I", 16))  # subchunk1size (16 for PCM)
    buffer.write(struct.pack("<H", 1))   # audio format 1 (PCM)
    buffer.write(struct.pack("<H", 1))   # num channels (1)
    buffer.write(struct.pack("<I", sample_rate))
    buffer.write(struct.pack("<I", sample_rate * 2))  # byte rate
    buffer.write(struct.pack("<H", 2))   # block align
    buffer.write(struct.pack("<H", 16))  # bits per sample
    # data subchunk
    buffer.write(b"data")
    buffer.write(struct.pack("<I", num_samples * 2))

    for i in range(num_samples):
        sample = int(32767.0 * 0.5 * math.sin(2.0 * math.pi * freq * i / sample_rate))
        buffer.write(struct.pack("<h", sample))

    return buffer.getvalue()


def generate_sample_pdf(title: str = "Official Gazette Notification") -> bytes:
    """Generate a minimal valid PDF 1.4 document stream."""
    content = f"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 55 >>
stream
BT
/F1 24 Tf
100 700 Td
({title}) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000206 00000 n 
trailer
<< /Size 5 /Root 1 0 R >>
startxref
310
%%EOF"""
    return content.encode("latin-1")


def generate_official_text() -> str:
    """Generate authentic press statement text."""
    unique_id = uuid.uuid4().hex[:8]
    return (
        f"OFFICIAL PRESS STATEMENT [Ref: {unique_id}]\n"
        "The Ministry of Information & Broadcasting hereby notifies all departments "
        "regarding the national content provenance guidelines established under Gazette 2026."
    )
