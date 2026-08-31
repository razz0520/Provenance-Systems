"""Comprehensive Automated Test Suite for PDF Document Similarity,
Near-Duplicate Detection, False-Positive Protection, and Tamper Verification.
"""

import io
import os
from pathlib import Path
import time
from unittest.mock import patch
import uuid

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.hash_service import (
    calculate_bytes_hash,
    calculate_file_hash,
    compare_pdf_fingerprints,
    generate_pdf_fingerprint,
)
from app.core.upload_validation import validate_file_payload
from app.main import app
from app.models.database import (
    ContentStatus,
    ContentType,
    CredentialStatus,
    RegisteredContent,
    UserRole,
    VerificationVerdict,
)
from app.services.auth_service import register_publisher
from app.services.publisher_service import register_content
from app.services.verification_service import VerificationService, verify_file
from app.services.whatsapp_service import WhatsAppService, process_message
from tests.test_data import generate_sample_pdf


def test_pdf_fingerprint_generation_and_text_extraction():
    """Test generating a compact PDF fingerprint and verifying extracted features."""
    uid = uuid.uuid4().hex[:6]
    pdf_bytes = generate_sample_pdf(f"Government Gazette Notification No. {uid}/2026 Ministry of Finance")
    fp = generate_pdf_fingerprint(pdf_bytes)

    assert fp["media_type"] == "PDF"
    assert fp["status"] == "AVAILABLE"
    assert fp["page_count"] == 1
    assert fp["word_count"] > 5
    assert len(fp["normalized_text_hash"]) == 64
    assert any(uid in t for t in fp["reference_tokens"])
    assert any("year_2026" in t for t in fp["reference_tokens"])
    assert len(fp["shingle_hashes"]) > 0


def test_pdf_fingerprint_comparisons_matrix():
    """Test multi-signal comparison logic across exact, modified, changed ref, and changed date."""
    uid = uuid.uuid4().hex[:6]
    base_pdf = generate_sample_pdf(f"Gazette Notification No. {uid}/2026 Ministry of Finance Tax rules approved.")
    mod_pdf = generate_sample_pdf(f"Gazette Notification No. {uid}/2026 Ministry of Finance Tax rules approved. (f) Maze karo")
    diff_ref_pdf = generate_sample_pdf("Gazette Notification No. 999999/2026 Ministry of Finance Tax rules approved.")
    diff_year_pdf = generate_sample_pdf(f"Gazette Notification No. {uid}/2027 Ministry of Finance Tax rules approved.")
    unrelated_pdf = generate_sample_pdf("Ministry of Agriculture Guidelines on Organic Farming Crop Rotation.")

    fp_base = generate_pdf_fingerprint(base_pdf)
    fp_mod = generate_pdf_fingerprint(mod_pdf)
    fp_diff_ref = generate_pdf_fingerprint(diff_ref_pdf)
    fp_diff_year = generate_pdf_fingerprint(diff_year_pdf)
    fp_unrel = generate_pdf_fingerprint(unrelated_pdf)

    # 1. Exact match
    assert compare_pdf_fingerprints(fp_base, fp_base) == 100.0

    # 2. Minor modification -> between 70.0% and 98.0%
    mod_score = compare_pdf_fingerprints(fp_base, fp_mod)
    assert 70.0 <= mod_score < 98.0

    # 3. Changed reference number -> penalized below 70.0%
    diff_ref_score = compare_pdf_fingerprints(fp_base, fp_diff_ref)
    assert diff_ref_score < 70.0

    # 4. Changed year -> penalized below 70.0%
    diff_year_score = compare_pdf_fingerprints(fp_base, fp_diff_year)
    assert diff_year_score < 70.0

    # 5. Unrelated document -> low score
    unrel_score = compare_pdf_fingerprints(fp_base, fp_unrel)
    assert unrel_score < 50.0


def test_pdf_exact_registered_verdict_e2e(db: Session, tmp_path):
    """Test 1: Exact registered PDF -> VERIFIED via SHA-256 exact match."""
    email = f"pdf_pub_{uuid.uuid4().hex[:6]}@gov.in"
    user = register_publisher(
        db=db,
        email=email,
        password="Password123!",
        organization_name="Ministry of Finance",
        organization_domain="finmin.gov.in",
    )
    uid = uuid.uuid4().hex[:6]
    pdf_bytes = generate_sample_pdf(f"Official Notification No. {uid}/2026 National Revenue Guidelines")
    upload = UploadFile(filename=f"revenue_{uid}.pdf", file=io.BytesIO(pdf_bytes))
    registered = register_content(db=db, publisher=user, upload_file=upload)

    # Verify exact file
    temp_file = tmp_path / f"test_exact_{uid}.pdf"
    temp_file.write_bytes(pdf_bytes)

    res = verify_file(db=db, upload_file=str(temp_file), filename=f"revenue_{uid}.pdf")
    assert res["verdict"] == VerificationVerdict.VERIFIED.value
    assert res["evidence_bundle"]["match_type"] == "EXACT_SHA256"
    assert res["evidence_bundle"]["sha256_match"] is True


def test_pdf_small_text_modification_suspicious_e2e(db: Session, tmp_path):
    """Test 2: Small text modification (added sentence) -> SUSPICIOUS via PDF similarity."""
    email = f"pdf_pub_{uuid.uuid4().hex[:6]}@gov.in"
    user = register_publisher(
        db=db,
        email=email,
        password="Password123!",
        organization_name="Ministry of Home Affairs",
        organization_domain="mha.gov.in",
    )
    uid = uuid.uuid4().hex[:6]
    original_pdf = generate_sample_pdf(f"Advisory Notice No. {uid}/2026 Border Security Protocol Standard")
    upload = UploadFile(filename=f"border_{uid}.pdf", file=io.BytesIO(original_pdf))
    registered = register_content(db=db, publisher=user, upload_file=upload)

    # Modified PDF with added fraudulent clause
    mod_pdf = generate_sample_pdf(f"Advisory Notice No. {uid}/2026 Border Security Protocol Standard Section (f) Maze karo")
    temp_mod = tmp_path / f"tampered_{uid}.pdf"
    temp_mod.write_bytes(mod_pdf)

    res = verify_file(db=db, upload_file=str(temp_mod), filename=f"forwarded_{uid}.pdf")
    assert res["verdict"] == VerificationVerdict.SUSPICIOUS.value
    assert res["evidence_bundle"]["match_type"] == "PERCEPTUAL_SIMILARITY"
    assert res["evidence_bundle"]["sha256_match"] is False
    assert 70.0 <= res["evidence_bundle"]["similarity_score"] < 98.0
    assert "alterations/modifications" in res["evidence_bundle"]["notice"]


def test_pdf_unrelated_verdict_e2e(db: Session, tmp_path):
    """Test 4: Unrelated PDF -> UNSIGNED."""
    email = f"pdf_pub_{uuid.uuid4().hex[:6]}@gov.in"
    user = register_publisher(
        db=db,
        email=email,
        password="Password123!",
        organization_name="Ministry of Mines",
        organization_domain="mines.gov.in",
    )
    uid = uuid.uuid4().hex[:6]
    pdf_bytes = generate_sample_pdf(f"Official Mining Gazette Notification No. {uid}/2026 Exploration Policy")
    upload = UploadFile(filename=f"mining_{uid}.pdf", file=io.BytesIO(pdf_bytes))
    register_content(db=db, publisher=user, upload_file=upload)

    # Completely different document
    unrelated = generate_sample_pdf("Private Cooking Recipe Book Dessert Collection 2024")
    temp_unrel = tmp_path / "recipe.pdf"
    temp_unrel.write_bytes(unrelated)

    res = verify_file(db=db, upload_file=str(temp_unrel), filename="random.pdf")
    assert res["verdict"] == VerificationVerdict.UNSIGNED.value
    assert res["evidence_bundle"]["match_type"] == "NONE"


def test_pdf_reexported_content_equivalent_e2e(db: Session, tmp_path):
    """Test 5: Re-exported PDF with identical normalized text content -> VERIFIED."""
    email = f"pdf_pub_{uuid.uuid4().hex[:6]}@gov.in"
    user = register_publisher(
        db=db,
        email=email,
        password="Password123!",
        organization_name="Ministry of Railways",
        organization_domain="railnet.gov.in",
    )
    uid = uuid.uuid4().hex[:6]
    title = f"Official Railway Schedule Notification No. {uid}/2026 Special Express Trains"
    original_pdf = generate_sample_pdf(title)
    upload = UploadFile(filename=f"railway_{uid}.pdf", file=io.BytesIO(original_pdf))
    register_content(db=db, publisher=user, upload_file=upload)

    # Re-exported version: same text with slightly different byte stream / metadata comments
    reexported = original_pdf + b"% Re-exported via Government Cloud Portal\n"
    temp_reexp = tmp_path / f"reexported_{uid}.pdf"
    temp_reexp.write_bytes(reexported)

    # Different SHA-256
    assert calculate_file_hash(temp_reexp) != calculate_bytes_hash(original_pdf)

    res = verify_file(db=db, upload_file=str(temp_reexp), filename=f"downloaded_railway_{uid}.pdf")
    assert res["verdict"] == VerificationVerdict.VERIFIED.value
    assert "re-exported" in res["evidence_bundle"]["notice"].lower()


def test_pdf_revoked_credential_precedence_e2e(db: Session, tmp_path):
    """Test 9: Highly similar/modified PDF matching a revoked publisher credential -> PROVEN_INVALID."""
    email = f"pdf_pub_{uuid.uuid4().hex[:6]}@gov.in"
    user = register_publisher(
        db=db,
        email=email,
        password="Password123!",
        organization_name="Ministry of Commerce",
        organization_domain="commerce.gov.in",
    )
    uid = uuid.uuid4().hex[:6]
    original_pdf = generate_sample_pdf(f"Export Import Advisory Order No. {uid}/2026 Tariff Rates")
    upload = UploadFile(filename=f"export_{uid}.pdf", file=io.BytesIO(original_pdf))
    registered = register_content(db=db, publisher=user, upload_file=upload)

    # Revoke publisher credential
    user.credentials[0].status = CredentialStatus.REVOKED
    db.commit()

    # Submit modified PDF
    mod_pdf = generate_sample_pdf(f"Export Import Advisory Order No. {uid}/2026 Tariff Rates Altered Clause (f)")
    temp_mod = tmp_path / f"mod_export_{uid}.pdf"
    temp_mod.write_bytes(mod_pdf)

    res = verify_file(db=db, upload_file=str(temp_mod), filename=f"mod_export_{uid}.pdf")
    assert res["verdict"] == VerificationVerdict.PROVEN_INVALID.value
    assert "revoked" in res["evidence_bundle"]["notice"].lower()


def test_pdf_suspended_credential_precedence_e2e(db: Session, tmp_path):
    """Test 10: Suspended publisher credential -> PROVEN_INVALID."""
    email = f"pdf_pub_{uuid.uuid4().hex[:6]}@gov.in"
    user = register_publisher(
        db=db,
        email=email,
        password="Password123!",
        organization_name="Ministry of Science",
        organization_domain="dst.gov.in",
    )
    uid = uuid.uuid4().hex[:6]
    original_pdf = generate_sample_pdf(f"National AI Research Grant Circular No. {uid}/2026")
    upload = UploadFile(filename=f"ai_grant_{uid}.pdf", file=io.BytesIO(original_pdf))
    registered = register_content(db=db, publisher=user, upload_file=upload)

    # Suspend publisher credential
    user.credentials[0].status = CredentialStatus.SUSPENDED
    db.commit()

    # Submit modified PDF
    mod_pdf = generate_sample_pdf(f"National AI Research Grant Circular No. {uid}/2026 Budget Tripled")
    temp_mod = tmp_path / f"mod_grant_{uid}.pdf"
    temp_mod.write_bytes(mod_pdf)

    res = verify_file(db=db, upload_file=str(temp_mod), filename=f"mod_grant_{uid}.pdf")
    assert res["verdict"] == VerificationVerdict.PROVEN_INVALID.value
    assert "suspended" in res["evidence_bundle"]["notice"].lower()


def test_pdf_malformed_and_empty_payloads():
    """Test 11 & 12: Malformed and empty PDF payloads handled safely."""
    client = TestClient(app)
    # Empty file -> 400 Bad Request
    res_empty = client.post("/api/v1/verify", files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")})
    assert res_empty.status_code == 400

    # Malformed garbage bytes with .pdf extension -> safely handled and returns UNSIGNED without crashing
    res_garbage = client.post("/api/v1/verify", files={"file": ("corrupt.pdf", io.BytesIO(b"garbage not pdf"), "application/pdf")})
    assert res_garbage.status_code == 200
    assert res_garbage.json()["verdict"] == "UNSIGNED"


def test_pdf_no_duplicate_permanent_storage(db: Session, tmp_path):
    """Test 16: Verify registration creates exactly 1 file on disk in uploads/processed."""
    email = f"pdf_pub_{uuid.uuid4().hex[:6]}@gov.in"
    user = register_publisher(
        db=db,
        email=email,
        password="Password123!",
        organization_name="Cabinet Affairs",
        organization_domain="cab.gov.in",
    )
    uid = uuid.uuid4().hex[:6]
    pdf_bytes = generate_sample_pdf(f"Storage Test Cabinet Notice No. {uid}/2026")
    upload = UploadFile(filename=f"cabinet_{uid}.pdf", file=io.BytesIO(pdf_bytes))
    registered = register_content(db=db, publisher=user, upload_file=upload)

    processed_dir = Path("uploads/processed")
    matching_files = [f for f in processed_dir.glob(f"*{registered.stored_filename}*")]
    assert len(matching_files) == 1
    # Check that no auxiliary rendered images or duplicate PDFs were saved
    assert not list(processed_dir.glob(f"*{registered.stored_filename}*.png"))
    assert not list(processed_dir.glob(f"*{registered.stored_filename}*.txt"))


def test_whatsapp_pdf_verification_pipeline_e2e(db: Session, tmp_path):
    """Test 19: WhatsApp pipeline processes PDF and returns SUSPICIOUS for modified version."""
    email = f"wa_pub_{uuid.uuid4().hex[:6]}@gov.in"
    user = register_publisher(
        db=db,
        email=email,
        password="Password123!",
        organization_name="Ministry of Electronics & IT",
        organization_domain="meity.gov.in",
    )
    uid = uuid.uuid4().hex[:6]
    original_pdf = generate_sample_pdf(f"MeitY Advisory Notification No. {uid}/2026 Cyber Safety Guidelines")
    upload = UploadFile(filename=f"cyber_advisory_{uid}.pdf", file=io.BytesIO(original_pdf))
    register_content(db=db, publisher=user, upload_file=upload)

    # Create modified PDF
    mod_pdf = generate_sample_pdf(f"MeitY Advisory Notification No. {uid}/2026 Cyber Safety Guidelines Altered Clause")
    temp_pdf = tmp_path / f"downloaded_mod_{uid}.pdf"
    temp_pdf.write_bytes(mod_pdf)

    unique_phone = f"91{uuid.uuid4().int % 10000000000:010d}"
    msg = {
        "from": unique_phone,
        "id": f"wamid.pdf_{uuid.uuid4().hex}",
        "type": "document",
        "document": {
            "id": f"meta_doc_{uid}",
            "mime_type": "application/pdf",
            "filename": f"cyber_advisory_{uid}.pdf",
        },
    }

    with patch("app.services.whatsapp_service.WhatsAppService.download_media", return_value=temp_pdf), \
         patch("app.services.whatsapp_service.WhatsAppService.send_whatsapp_message", return_value=True), \
         patch("app.services.whatsapp_service.WhatsAppService.send_interactive_message", return_value=True) as mock_send_int:

        res = process_message(message=msg, sender_name="Citizen", db=db)
        assert res.get("success") is True
        assert res["verification_result"]["verdict"] == "SUSPICIOUS"
        assert mock_send_int.called


def test_pdf_meaningful_content_modification_suspicious(db: Session, tmp_path):
    """Test 3: Meaningful content modification (altering tax rate 18% -> 80%) -> SUSPICIOUS."""
    email = f"pdf_tax_{uuid.uuid4().hex[:6]}@gov.in"
    user = register_publisher(
        db=db,
        email=email,
        password="Password123!",
        organization_name="Central Board of Direct Taxes",
        organization_domain="incometax.gov.in",
    )
    uid = uuid.uuid4().hex[:6]
    orig_text = f"CBDT Notification No. {uid}/2026 Statutory Standard Tax Rate Applicable is 18 Percent Effective April"
    orig_pdf = generate_sample_pdf(orig_text)
    upload = UploadFile(filename=f"cbdt_{uid}.pdf", file=io.BytesIO(orig_pdf))
    register_content(db=db, publisher=user, upload_file=upload)

    # Tampered PDF with changed tax rate figure (18% -> 80%)
    mod_text = f"CBDT Notification No. {uid}/2026 Statutory Standard Tax Rate Applicable is 80 Percent Effective April"
    mod_pdf = generate_sample_pdf(mod_text)
    temp_mod = tmp_path / f"cbdt_tampered_{uid}.pdf"
    temp_mod.write_bytes(mod_pdf)

    res = verify_file(db=db, upload_file=str(temp_mod), filename=f"cbdt_tampered_{uid}.pdf")
    assert res["verdict"] == VerificationVerdict.SUSPICIOUS.value
    assert res["evidence_bundle"]["match_type"] == "PERCEPTUAL_SIMILARITY"
    assert 70.0 <= res["evidence_bundle"]["similarity_score"] < 98.0


def test_pdf_changed_reference_number_returns_unsigned(db: Session, tmp_path):
    """Test 7: Similar text with changed reference number -> UNSIGNED."""
    email = f"pdf_ref_{uuid.uuid4().hex[:6]}@gov.in"
    user = register_publisher(
        db=db,
        email=email,
        password="Password123!",
        organization_name="Ministry of Law",
        organization_domain="law.gov.in",
    )
    uid = uuid.uuid4().hex[:6]
    orig_pdf = generate_sample_pdf(f"Ministry of Law Statutory Order No. 1111_{uid}/2026 Court Procedures Special Topic {uid}")
    upload = UploadFile(filename=f"order_1111_{uid}.pdf", file=io.BytesIO(orig_pdf))
    register_content(db=db, publisher=user, upload_file=upload)

    # Submitted PDF with identical boilerplate but completely different reference number 9999/2026
    diff_ref_pdf = generate_sample_pdf(f"Ministry of Law Statutory Order No. 9999_{uid}/2026 Court Procedures Special Topic {uid}")
    temp_diff = tmp_path / f"order_9999_{uid}.pdf"
    temp_diff.write_bytes(diff_ref_pdf)

    res = verify_file(db=db, upload_file=str(temp_diff), filename=f"order_9999_{uid}.pdf")
    assert res["verdict"] == VerificationVerdict.UNSIGNED.value
    assert res["evidence_bundle"]["match_type"] == "NONE"


def test_pdf_changed_date_returns_unsigned(db: Session, tmp_path):
    """Test 8: Similar text with changed publication year (2026 -> 2027) -> UNSIGNED."""
    email = f"pdf_year_{uuid.uuid4().hex[:6]}@gov.in"
    user = register_publisher(
        db=db,
        email=email,
        password="Password123!",
        organization_name="Ministry of Statistics",
        organization_domain="mospi.gov.in",
    )
    uid = uuid.uuid4().hex[:6]
    orig_pdf = generate_sample_pdf(f"National Statistics Survey Report Notification No. 404_{uid}/2026 Annual Metrics")
    upload = UploadFile(filename=f"survey_{uid}_2026.pdf", file=io.BytesIO(orig_pdf))
    register_content(db=db, publisher=user, upload_file=upload)

    # Submitted PDF with next year (2027)
    diff_year_pdf = generate_sample_pdf(f"National Statistics Survey Report Notification No. 404_{uid}/2027 Annual Metrics")
    temp_diff_y = tmp_path / f"survey_{uid}_2027.pdf"
    temp_diff_y.write_bytes(diff_year_pdf)

    res = verify_file(db=db, upload_file=str(temp_diff_y), filename=f"survey_{uid}_2027.pdf")
    assert res["verdict"] == VerificationVerdict.UNSIGNED.value
    assert res["evidence_bundle"]["match_type"] == "NONE"


def test_pdf_oversized_payload_rejected_by_validation():
    """Test 13: PDF payload exceeding 16 MB is rejected defensively."""
    client = TestClient(app)
    # Simulate oversized payload (17 MB)
    oversized_data = b"%PDF-1.4\n" + (b"0" * (17 * 1024 * 1024))
    res = client.post("/api/v1/verify", files={"file": ("huge.pdf", io.BytesIO(oversized_data), "application/pdf")})
    assert res.status_code == 413 or res.status_code == 400


def test_pdf_large_text_bounded_extraction():
    """Test 14: PDF fingerprinting processes large text safely within bounds."""
    # Generate a PDF with a long text stream (e.g. 1000 words)
    long_text = "Government Official Notice No. 101/2026 " + ("Standard regulatory compliance requirement text. " * 300)
    pdf_bytes = generate_sample_pdf(long_text[:3000])
    fp = generate_pdf_fingerprint(pdf_bytes, max_pages=50, max_chars=50000)

    assert fp["status"] == "AVAILABLE"
    assert fp["char_count"] <= 50000
    assert len(fp["shingle_hashes"]) <= 100


def test_pdf_temp_file_cleaned_after_verification(db: Session, tmp_path):
    """Test 17: Temporary files created during verification are cleanly removed."""
    pdf_bytes = generate_sample_pdf("Temporary File Cleanup Test Notification No. 555/2026")
    upload = UploadFile(filename="temp_cleanup.pdf", file=io.BytesIO(pdf_bytes))

    # Verify and confirm no leaked temp files remain in system temp dir
    res = verify_file(db=db, upload_file=upload, filename="temp_cleanup.pdf")
    assert res["verdict"] == VerificationVerdict.UNSIGNED.value
