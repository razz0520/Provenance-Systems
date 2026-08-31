"""Unit and integration tests for WhatsApp Service, Webhook Endpoints, Media Processing,
Rate Limiting, Retries, Caching, and Outbound Cloud API Dispatch.
"""

import io
import json
import os
from pathlib import Path
import tempfile
import time
from unittest.mock import MagicMock, patch
import uuid
import httpx
import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models.database import (
    ContentType,
    Credential,
    CredentialStatus,
    CredentialType,
    RegisteredContent,
    User,
    UserRole,
    VerificationVerdict,
)
from app.services.auth_service import register_publisher
from app.services.publisher_service import register_content
from app.services.whatsapp_service import (
    WhatsAppService,
    cleanup_temp_files,
    download_media,
    execute_with_retry,
    format_explainer_message,
    format_help_response,
    format_invalid_response,
    format_proof_message,
    format_rate_limit_response,
    format_suspicious_response,
    format_unsigned_response,
    format_verification_result,
    format_verified_response,
    handle_media_message,
    handle_webhook,
    process_message,
    process_through_verification,
    send_interactive_message,
    send_whatsapp_message,
    validate_media_file,
    verify_webhook,
)
from tests.test_data import (
    generate_compressed_image,
    generate_distinct_image,
    generate_modified_image,
    generate_sample_audio,
    generate_sample_image,
    generate_sample_pdf,
)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


# ============================================================================
# 1. Webhook Verification (GET Challenge) Tests
# ============================================================================

def test_verify_webhook_success():
    """Test webhook verification with valid token."""
    mode = "subscribe"
    token = settings.WHATSAPP_VERIFY_TOKEN
    challenge = "1234567890"

    result = verify_webhook(mode=mode, token=token, challenge=challenge)
    assert result == challenge


def test_verify_webhook_invalid_token():
    """Test webhook verification failure with invalid token."""
    with pytest.raises(ValueError):
        verify_webhook(mode="subscribe", token="wrong-token", challenge="12345")


def test_webhook_get_endpoint(client):
    """Test GET /api/v1/webhook/whatsapp with Meta Hub query parameters."""
    response = client.get(
        "/api/v1/webhook/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": settings.WHATSAPP_VERIFY_TOKEN,
            "hub.challenge": "987654321",
        },
    )
    assert response.status_code == 200
    assert response.text == "987654321"


def test_webhook_get_endpoint_forbidden(client):
    """Test GET /api/v1/webhook/whatsapp with mismatched token returns 403."""
    response = client.get(
        "/api/v1/webhook/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "invalid-token",
            "hub.challenge": "987654321",
        },
    )
    assert response.status_code == 403


# ============================================================================
# 2. Response Templates, Verdict Policies, and Proof Messages
# ============================================================================

def test_response_templates():
    """Test WhatsApp Markdown response message formatting and button payloads."""
    # 1. Verified Response - exactly 1 button: btn_proof
    verified_evidence = {
        "publisher_organization": "Ministry of Electronics & IT",
        "original_filename": "official_statement.pdf",
        "chain_block_id": 42,
        "signature_valid": True,
        "sha256_match": True,
        "perceptual_hash": {"similarity_percentage": 100},
    }
    ver_payload = format_verified_response(verified_evidence, confidence=0.99)
    assert "Verified official content" in ver_payload["body_text"]
    assert "Ministry of Electronics & IT" in ver_payload["body_text"]
    assert len(ver_payload["buttons"]) == 1
    assert ver_payload["buttons"][0]["id"] == "btn_proof"
    assert ver_payload["buttons"][0]["title"] == "How was this checked"

    # 2. Suspicious Response - exactly 2 buttons: btn_proof, btn_report
    susp_evidence = {
        "publisher_organization": "Press Information Bureau",
        "perceptual_hash": {"similarity_percentage": 78},
        "notice": "Media altered",
    }
    susp_payload = format_suspicious_response(susp_evidence, confidence=0.78)
    assert "This appears to be a modified version" in susp_payload["body_text"]
    assert "Press Information Bureau" in susp_payload["body_text"]
    assert len(susp_payload["buttons"]) == 2
    assert [b["id"] for b in susp_payload["buttons"]] == ["btn_proof", "btn_report"]
    assert susp_payload["buttons"][1]["title"] == "Report this content"

    # 3. Unsigned Response - exactly 2 buttons: btn_proof, btn_report
    unsign_payload = format_unsigned_response()
    assert "We can't confirm this is official government content" in unsign_payload["body_text"]
    assert len(unsign_payload["buttons"]) == 2
    assert [b["id"] for b in unsign_payload["buttons"]] == ["btn_proof", "btn_report"]

    # 4. Invalid Response - exactly 2 buttons: btn_proof, btn_report
    inv_payload = format_invalid_response("Corrupted file format")
    assert "This does not match any official record" in inv_payload["body_text"]
    assert len(inv_payload["buttons"]) == 2
    assert [b["id"] for b in inv_payload["buttons"]] == ["btn_proof", "btn_report"]

    # 5. Rate Limit Response
    rl_text = format_rate_limit_response()
    assert "Rate Limit Exceeded" in rl_text


def test_button_policy_per_verdict():
    """Verify verdict-specific button sets and absence of btn_changed/Evidence Matrix."""
    ver_payload = format_verified_response({"publisher_organization": "Gov"})
    susp_payload = format_suspicious_response({"publisher_organization": "Gov"})
    unsign_payload = format_unsigned_response()
    inv_payload = format_invalid_response()

    # VERIFIED: exactly btn_proof
    assert [b["id"] for b in ver_payload["buttons"]] == ["btn_proof"]

    # SUSPICIOUS / UNSIGNED / INVALID: exactly btn_proof + btn_report
    assert [b["id"] for b in susp_payload["buttons"]] == ["btn_proof", "btn_report"]
    assert [b["id"] for b in unsign_payload["buttons"]] == ["btn_proof", "btn_report"]
    assert [b["id"] for b in inv_payload["buttons"]] == ["btn_proof", "btn_report"]

    # Never show btn_changed anywhere
    for payload in [ver_payload, susp_payload, unsign_payload, inv_payload]:
        for btn in payload["buttons"]:
            assert btn["id"] != "btn_changed"
            assert "What changed" not in btn["title"]
            assert "Evidence Matrix" not in btn["title"]


def test_verdict_bodies_length_and_formatting():
    """Ensure all verdict bodies are <1024 chars and do not contain forbidden markdown."""
    evidence = {
        "publisher_organization": "Ministry of Information & Broadcasting",
        "content_type": "video",
        "created_at": "2026-08-20T10:00:00Z",
    }

    verdict_payloads = [
        format_verified_response(evidence),
        format_suspicious_response(evidence),
        format_unsigned_response(),
        format_invalid_response(),
        format_help_response("Citizen"),
    ]

    for payload in verdict_payloads:
        body = payload["body_text"]
        assert len(body) < 1024, f"Body exceeded 1024 characters ({len(body)} chars): {body}"
        assert "**" not in body, f"Forbidden '**' found in body: {body}"
        assert "#" not in body, f"Forbidden '#' found in body: {body}"
        for btn in payload["buttons"]:
            assert len(btn["title"]) <= 20, f"Button title exceeds 20 characters: '{btn['title']}' ({len(btn['title'])})"


def test_button_titles_under_20_chars():
    """Fail loudly if any interactive button title exceeds Meta Cloud API 20 char limit."""
    ver_payload = format_verified_response({"publisher_organization": "Gov"})
    susp_payload = format_suspicious_response({"publisher_organization": "Gov"})
    unsign_payload = format_unsigned_response()
    inv_payload = format_invalid_response()
    help_payload = format_help_response("Citizen")

    all_buttons = (
        ver_payload["buttons"]
        + susp_payload["buttons"]
        + unsign_payload["buttons"]
        + inv_payload["buttons"]
        + help_payload["buttons"]
    )

    for btn in all_buttons:
        assert len(btn["title"]) <= 20, f"Button title '{btn['title']}' is {len(btn['title'])} chars (max 20)"


def test_onboarding_brevity_and_cleanliness():
    """Verify onboarding message is concise and contains no raw crypto jargon."""
    help_payload = format_help_response("Rahul")
    body = help_payload["body_text"]

    assert len(body) < 1024
    assert "Rahul" in body
    assert "SHA-256" not in body
    assert "Ed25519" not in body
    assert "C2PA" not in body
    assert len(help_payload["buttons"]) == 1
    assert help_payload["buttons"][0]["id"] == "btn_explainer"
    assert help_payload["buttons"][0]["title"] == "What is verified?"


def test_proof_message_relevant_signals_only():
    """Verify proof message only renders signals actually present in the evidence."""
    # Case 1: Only SHA-256 match present (no signature, no perceptual, no chain)
    result_sha_only = {
        "verdict": "VERIFIED",
        "evidence_bundle": {
            "sha256_match": True,
            "digital_signature": None,
            "manifest_data": None,
            "chain_block_id": None,
            "perceptual_match_status": "NOT_APPLICABLE",
        },
    }
    proof_sha = format_proof_message(result_sha_only)
    assert "Matches the original file" in proof_sha
    assert "SHA-256 hash match confirmed" in proof_sha
    assert "Digitally signed" not in proof_sha
    assert "C2PA" not in proof_sha
    assert "tamper-proof ledger" not in proof_sha

    # Case 2: Full evidence present
    result_full = {
        "verdict": "VERIFIED",
        "evidence_bundle": {
            "sha256_match": True,
            "perceptual_match_status": "EXACT_MATCH",
            "digital_signature": "sig_hex_data",
            "signature_valid": True,
            "manifest_data": {"claim": "data"},
            "manifest_valid": True,
            "chain_block_id": 99,
            "chain_integrity": True,
        },
    }
    proof_full = format_proof_message(result_full)
    assert "SHA-256 hash match confirmed" in proof_full
    assert "Perceptual fingerprint" in proof_full
    assert "Ed25519 cryptographic signature verified" in proof_full
    assert "C2PA-standard provenance manifest" in proof_full
    assert "Hash-chain ledger block #99 integrity confirmed" in proof_full
    assert len(proof_full) < 1024
    assert "**" not in proof_full

    # Case 3: Unsigned fallback
    result_unsigned = {
        "verdict": "UNSIGNED",
        "evidence_bundle": {
            "sha256_match": False,
            "match_type": "NONE",
        },
    }
    proof_unsigned = format_proof_message(result_unsigned)
    assert "no matching records found" in proof_unsigned


def test_proof_message_partial_signals():
    """Verify proof message accurately adapts when only manifest or signature is present."""
    # Manifest only
    res_manifest = {
        "verdict": "VERIFIED",
        "evidence_bundle": {
            "manifest_data": {"format": "C2PA"},
            "manifest_valid": True,
            "sha256_match": False,
        },
    }
    proof_manifest = format_proof_message(res_manifest)
    assert "C2PA-standard provenance manifest" in proof_manifest
    assert "Ed25519 cryptographic signature" not in proof_manifest

    # Signature only
    res_sig = {
        "verdict": "VERIFIED",
        "evidence_bundle": {
            "digital_signature": "valid_sig_12345",
            "signature_valid": True,
            "sha256_match": False,
        },
    }
    proof_sig = format_proof_message(res_sig)
    assert "Ed25519 cryptographic signature verified" in proof_sig
    assert "C2PA" not in proof_sig

    # Tampered / Invalid
    res_invalid = {
        "verdict": "PROVEN_INVALID",
        "evidence_bundle": {
            "sha256_match": False,
            "signature_valid": False,
            "manifest_valid": False,
            "chain_integrity": False,
        },
    }
    proof_invalid = format_proof_message(res_invalid)
    assert "authenticity check" in proof_invalid.lower()
    assert "cryptographic signature or manifest validation failed" in proof_invalid.lower()


# ============================================================================
# 3. Interactive Button Routing Tests
# ============================================================================

def test_interactive_button_routing(db: Session):
    """Test interactive button responses for btn_proof, btn_report, and btn_explainer."""
    phone = f"91{uuid.uuid4().int % 10000000000:010d}"

    # 1. Test btn_explainer
    msg_explainer = {
        "from": phone,
        "id": f"wamid.{uuid.uuid4().hex}",
        "type": "interactive",
        "interactive": {
            "type": "button_reply",
            "button_reply": {"id": "btn_explainer", "title": "What is verified?"},
        },
    }
    with patch("app.services.whatsapp_service.WhatsAppService.send_whatsapp_message") as mock_send:
        mock_send.return_value = True
        res = process_message(message=msg_explainer, sender_name="Citizen", db=db)
        assert res.get("type") == "explainer_sent"
        assert mock_send.called
        sent_text = mock_send.call_args[1]["message_text"]
        assert "What does 'verified' mean?" in sent_text
        assert "SHA-256" in sent_text

    # 2. Test btn_report (PIB Fact Check Portal redirect)
    msg_report = {
        "from": phone,
        "id": f"wamid.{uuid.uuid4().hex}",
        "type": "interactive",
        "interactive": {
            "type": "button_reply",
            "button_reply": {"id": "btn_report", "title": "Report this content"},
        },
    }
    with patch("app.services.whatsapp_service.WhatsAppService.send_whatsapp_message") as mock_send:
        mock_send.return_value = True
        res = process_message(message=msg_report, sender_name="Citizen", db=db)
        assert res.get("type") == "report_redirect"
        assert mock_send.called
        sent_text = mock_send.call_args[1]["message_text"]
        assert "https://factcheck.pib.gov.in/" in sent_text
        assert "Report this content officially" in sent_text
        assert "Our system does not handle government complaints directly" in sent_text
        # Must never claim report was stored or submitted
        assert "stored" not in sent_text.lower()
        assert "submitted" not in sent_text.lower() or "submit this content for investigation" in sent_text.lower()

    # 3. Test btn_proof
    msg_proof = {
        "from": phone,
        "id": f"wamid.{uuid.uuid4().hex}",
        "type": "interactive",
        "interactive": {
            "type": "button_reply",
            "button_reply": {"id": "btn_proof", "title": "How was this checked"},
        },
    }
    with patch("app.services.whatsapp_service.WhatsAppService.send_whatsapp_message") as mock_send:
        mock_send.return_value = True
        res = process_message(message=msg_proof, sender_name="Citizen", db=db)
        assert res.get("type") == "proof_sent"
        assert mock_send.called


def test_unknown_button_id_handling(db: Session):
    """Test handling of unexpected or legacy interactive button IDs."""
    phone = f"91{uuid.uuid4().int % 10000000000:010d}"
    msg = {
        "from": phone,
        "id": f"wamid.{uuid.uuid4().hex}",
        "type": "interactive",
        "interactive": {
            "type": "button_reply",
            "button_reply": {"id": "btn_unknown_custom", "title": "Other Action"},
        },
    }
    with patch("app.services.whatsapp_service.WhatsAppService.send_whatsapp_message") as mock_send:
        mock_send.return_value = True
        res = process_message(message=msg, sender_name="Citizen", db=db)
        assert res.get("type") == "unknown_button"
        assert mock_send.called
        sent_text = mock_send.call_args[1]["message_text"]
        assert "Please send an image, video, audio clip, or text" in sent_text


# ============================================================================
# 4. Text and Media Pipeline Execution (Mocked Meta API)
# ============================================================================

def test_process_text_greeting(db: Session):
    """Test text greeting / help triggers interactive onboarding menu."""
    unique_phone = f"91{uuid.uuid4().int % 10000000000:010d}"
    message = {
        "from": unique_phone,
        "id": f"wamid.{uuid.uuid4().hex}",
        "type": "text",
        "text": {"body": "help"},
    }
    with patch("app.services.whatsapp_service.WhatsAppService.send_interactive_message") as mock_send_int:
        mock_send_int.return_value = True
        res = process_message(message=message, sender_name="John Doe", db=db)
        assert res.get("type") == "help"
        assert mock_send_int.called
        sent_body = mock_send_int.call_args[1]["body_text"]
        assert "Welcome John Doe!" in sent_body


def test_process_text_verification(db: Session):
    """Test text verification against registered official statement sends interactive verdict."""
    email = f"whatsapp_pub_{uuid.uuid4().hex[:6]}@gov.in"
    user = register_publisher(
        db=db,
        email=email,
        password="PublisherPassword#123",
        organization_name="Ministry of Information",
        organization_domain="gov.in",
    )

    official_text = f"Official Press Release: National AI Framework Launched {uuid.uuid4().hex[:6]}."
    upload_file = UploadFile(
        filename="press_release.txt",
        file=io.BytesIO(official_text.encode("utf-8")),
    )
    register_content(
        db=db,
        publisher=user,
        upload_file=upload_file,
    )

    unique_phone = f"91{uuid.uuid4().int % 10000000000:010d}"
    message = {
        "from": unique_phone,
        "id": f"wamid.{uuid.uuid4().hex}",
        "type": "text",
        "text": {"body": official_text},
    }

    with patch("app.services.whatsapp_service.WhatsAppService.send_interactive_message") as mock_send_int:
        mock_send_int.return_value = True
        res = process_message(message=message, sender_name="Citizen", db=db)
        assert res.get("verdict") == "VERIFIED"
        assert mock_send_int.called
        sent_body = mock_send_int.call_args[1]["body_text"]
        assert "Verified official content" in sent_body
        assert "Ministry of Information" in sent_body


def test_media_pipeline_image_verified(db: Session, tmp_path):
    """Test image webhook payload -> download -> verification -> VERIFIED verdict response."""
    # 1. Register official image
    email = f"wa_img_{uuid.uuid4().hex[:6]}@gov.in"
    user = register_publisher(
        db=db,
        email=email,
        password="Password#123",
        organization_name="Press Information Bureau",
        organization_domain="gov.in",
    )
    img_bytes = generate_sample_image(f"OFFICIAL RELEASE {uuid.uuid4().hex[:6]}")
    upload_file = UploadFile(filename="official.png", file=io.BytesIO(img_bytes))
    register_content(db=db, publisher=user, upload_file=upload_file)

    # 2. Write temp image for mock download
    temp_img = tmp_path / "downloaded.png"
    temp_img.write_bytes(img_bytes)

    unique_phone = f"91{uuid.uuid4().int % 10000000000:010d}"
    msg = {
        "from": unique_phone,
        "id": f"wamid.img_{uuid.uuid4().hex}",
        "type": "image",
        "image": {
            "id": "meta_img_id_101",
            "mime_type": "image/png",
        },
    }

    with patch("app.services.whatsapp_service.WhatsAppService.download_media") as mock_dl, \
         patch("app.services.whatsapp_service.WhatsAppService.send_whatsapp_message") as mock_send, \
         patch("app.services.whatsapp_service.WhatsAppService.send_interactive_message") as mock_send_int:
        mock_dl.return_value = str(temp_img)
        mock_send.return_value = True
        mock_send_int.return_value = True

        res = process_message(message=msg, sender_name="Citizen", db=db)
        assert res.get("success") is True
        assert res["verification_result"]["verdict"] == "VERIFIED"
        assert mock_send_int.called
        sent_body = mock_send_int.call_args[1]["body_text"]
        assert "Verified official content" in sent_body


def test_media_pipeline_audio_verified(db: Session, tmp_path):
    """Test audio webhook payload -> download -> verification -> VERIFIED verdict response."""
    email = f"wa_aud_{uuid.uuid4().hex[:6]}@gov.in"
    user = register_publisher(
        db=db,
        email=email,
        password="Password#123",
        organization_name="All India Radio",
        organization_domain="gov.in",
    )
    audio_bytes = generate_sample_audio(duration_sec=1.0, freq=520.0)
    upload_file = UploadFile(filename="broadcast.wav", file=io.BytesIO(audio_bytes))
    register_content(db=db, publisher=user, upload_file=upload_file)

    temp_aud = tmp_path / "downloaded.wav"
    temp_aud.write_bytes(audio_bytes)

    unique_phone = f"91{uuid.uuid4().int % 10000000000:010d}"
    msg = {
        "from": unique_phone,
        "id": f"wamid.aud_{uuid.uuid4().hex}",
        "type": "audio",
        "audio": {
            "id": "meta_aud_id_202",
            "mime_type": "audio/wav",
        },
    }

    with patch("app.services.whatsapp_service.WhatsAppService.download_media") as mock_dl, \
         patch("app.services.whatsapp_service.WhatsAppService.send_whatsapp_message") as mock_send, \
         patch("app.services.whatsapp_service.WhatsAppService.send_interactive_message") as mock_send_int:
        mock_dl.return_value = str(temp_aud)
        mock_send.return_value = True
        mock_send_int.return_value = True

        res = process_message(message=msg, sender_name="Citizen", db=db)
        assert res.get("success") is True
        assert res["verification_result"]["verdict"] == "VERIFIED"
        assert mock_send_int.called


def test_media_pipeline_document_pdf_verified(db: Session, tmp_path):
    """Test PDF document webhook payload -> download -> verification -> VERIFIED verdict response."""
    email = f"wa_doc_{uuid.uuid4().hex[:6]}@gov.in"
    user = register_publisher(
        db=db,
        email=email,
        password="Password#123",
        organization_name="Cabinet Secretariat",
        organization_domain="gov.in",
    )
    pdf_bytes = generate_sample_pdf(f"Gazette Notice {uuid.uuid4().hex[:6]}")
    upload_file = UploadFile(filename="gazette.pdf", file=io.BytesIO(pdf_bytes))
    register_content(db=db, publisher=user, upload_file=upload_file)

    temp_pdf = tmp_path / "downloaded.pdf"
    temp_pdf.write_bytes(pdf_bytes)

    unique_phone = f"91{uuid.uuid4().int % 10000000000:010d}"
    msg = {
        "from": unique_phone,
        "id": f"wamid.doc_{uuid.uuid4().hex}",
        "type": "document",
        "document": {
            "id": "meta_doc_id_303",
            "mime_type": "application/pdf",
            "filename": "gazette.pdf",
        },
    }

    with patch("app.services.whatsapp_service.WhatsAppService.download_media") as mock_dl, \
         patch("app.services.whatsapp_service.WhatsAppService.send_whatsapp_message") as mock_send, \
         patch("app.services.whatsapp_service.WhatsAppService.send_interactive_message") as mock_send_int:
        mock_dl.return_value = str(temp_pdf)
        mock_send.return_value = True
        mock_send_int.return_value = True

        res = process_message(message=msg, sender_name="Citizen", db=db)
        assert res.get("success") is True
        assert res["verification_result"]["verdict"] == "VERIFIED"
        assert mock_send_int.called


def test_media_pipeline_video_unsigned(db: Session, tmp_path):
    """Test unregistered video webhook payload -> download -> verification -> UNSIGNED verdict response."""
    temp_vid = tmp_path / "sample_unreg.mp4"
    temp_vid.write_bytes(os.urandom(2048))

    unique_phone = f"91{uuid.uuid4().int % 10000000000:010d}"
    msg = {
        "from": unique_phone,
        "id": f"wamid.vid_{uuid.uuid4().hex}",
        "type": "video",
        "video": {
            "id": "meta_vid_id_404",
            "mime_type": "video/mp4",
        },
    }

    with patch("app.services.whatsapp_service.WhatsAppService.download_media") as mock_dl, \
         patch("app.services.whatsapp_service.WhatsAppService.send_whatsapp_message") as mock_send, \
         patch("app.services.whatsapp_service.WhatsAppService.send_interactive_message") as mock_send_int:
        mock_dl.return_value = str(temp_vid)
        mock_send.return_value = True
        mock_send_int.return_value = True

        res = process_message(message=msg, sender_name="Citizen", db=db)
        assert res.get("success") is True
        assert res["verification_result"]["verdict"] == "UNSIGNED"
        assert mock_send_int.called
        sent_body = mock_send_int.call_args[1]["body_text"]
        assert "We can't confirm this is official government content" in sent_body


# ============================================================================
# 5. Media Download, Validation, and Failure Recovery Tests
# ============================================================================

def test_download_media_success(tmp_path):
    """Test downloading media binary via mocked Meta Graph API endpoints."""
    meta_response = httpx.Response(
        200,
        json={"url": "https://cdn.whatsapp.net/v18.0/binary123", "mime_type": "image/png"},
        request=httpx.Request("GET", "https://graph.facebook.com/v18.0/media_101"),
    )
    binary_content = generate_sample_image("MOCK DOWNLOAD TEST")
    binary_response = httpx.Response(
        200,
        content=binary_content,
        request=httpx.Request("GET", "https://cdn.whatsapp.net/v18.0/binary123"),
    )

    with patch("httpx.Client.get") as mock_get:
        mock_get.side_effect = [meta_response, binary_response]
        file_path = download_media(media_id="media_101", mime_type="image/png")
        assert file_path is not None
        assert os.path.exists(file_path)
        assert os.path.getsize(file_path) == len(binary_content)
        # Cleanup
        cleanup_temp_files(file_path)
        assert not os.path.exists(file_path)


def test_download_media_failures():
    """Test failure branches in download_media (missing token, 404 metadata, 500 binary)."""
    # 1. Missing token
    with patch.object(settings, "WHATSAPP_ACCESS_TOKEN", ""):
        assert download_media("media_no_token") is None

    # 2. Metadata HTTP 404
    res_404 = httpx.Response(404, request=httpx.Request("GET", "https://meta.test"))
    with patch("httpx.Client.get", return_value=res_404):
        assert download_media("media_404") is None

    # 3. Missing download URL in JSON
    res_no_url = httpx.Response(200, json={}, request=httpx.Request("GET", "https://meta.test"))
    with patch("httpx.Client.get", return_value=res_no_url):
        assert download_media("media_no_url") is None

    # 4. Binary download HTTP 500
    res_meta_ok = httpx.Response(200, json={"url": "http://cdn.test"}, request=httpx.Request("GET", "http://meta.test"))
    res_bin_500 = httpx.Response(500, request=httpx.Request("GET", "http://cdn.test"))
    with patch("httpx.Client.get") as mock_get, patch("time.sleep"):
        mock_get.side_effect = [res_meta_ok, res_bin_500, res_bin_500, res_bin_500]
        assert download_media("media_bin_fail") is None


def test_validate_media_file_scenarios(tmp_path):
    """Test file existence, size thresholds, and empty-file rejection in validate_media_file."""
    # 1. Non-existent file
    assert validate_media_file("/path/does/not/exist.png") is False
    assert validate_media_file("") is False

    # 2. Empty 0-byte file
    empty_file = tmp_path / "empty.png"
    empty_file.write_bytes(b"")
    assert validate_media_file(str(empty_file)) is False

    # 3. Valid normal file
    valid_file = tmp_path / "valid.png"
    valid_file.write_bytes(b"PNG_DATA_HEADER")
    assert validate_media_file(str(valid_file)) is True

    # 4. File exceeding MAX_UPLOAD_SIZE
    with patch.object(settings, "MAX_UPLOAD_SIZE", 10):
        oversized_file = tmp_path / "large.png"
        oversized_file.write_bytes(b"0" * 50)
        assert validate_media_file(str(oversized_file)) is False


def test_cleanup_temp_files_safety(tmp_path):
    """Test guaranteed safe temp file cleanup."""
    # 1. Normal deletion
    f = tmp_path / "temp.bin"
    f.write_bytes(b"temp")
    assert os.path.exists(f)
    cleanup_temp_files(str(f))
    assert not os.path.exists(f)

    # 2. Safely handles None and non-existent paths
    cleanup_temp_files(None)
    cleanup_temp_files("/non/existent/file.bin")


def test_media_missing_id_in_payload(db: Session):
    """Test handling when media payload is missing the Meta media ID."""
    unique_phone = f"91{uuid.uuid4().int % 10000000000:010d}"
    msg = {
        "from": unique_phone,
        "id": f"wamid.{uuid.uuid4().hex}",
        "type": "image",
        "image": {},  # Missing 'id'
    }
    with patch("app.services.whatsapp_service.WhatsAppService.send_whatsapp_message") as mock_send:
        mock_send.return_value = True
        res = process_message(message=msg, sender_name="Citizen", db=db)
        assert res.get("error") == "missing_media_id"
        assert mock_send.called
        sent_text = mock_send.call_args[1]["message_text"]
        assert "Could not read attached media file identifier" in sent_text


def test_media_download_failure_handling(db: Session):
    """Test user notification when media download from Meta servers fails."""
    unique_phone = f"91{uuid.uuid4().int % 10000000000:010d}"
    msg = {
        "from": unique_phone,
        "id": f"wamid.{uuid.uuid4().hex}",
        "type": "image",
        "image": {"id": "fail_media_id"},
    }
    with patch("app.services.whatsapp_service.WhatsAppService.download_media", return_value=None), \
         patch("app.services.whatsapp_service.WhatsAppService.send_whatsapp_message") as mock_send:
        mock_send.return_value = True
        res = process_message(message=msg, sender_name="Citizen", db=db)
        assert res.get("success") is False
        assert "Failed to download" in res.get("error")
        assert mock_send.called


def test_unsupported_message_type_handling(db: Session):
    """Test unsupported message types (location, contacts, sticker) send citizen guide."""
    unique_phone = f"91{uuid.uuid4().int % 10000000000:010d}"
    msg = {
        "from": unique_phone,
        "id": f"wamid.{uuid.uuid4().hex}",
        "type": "location",
        "location": {"latitude": 28.6139, "longitude": 77.2090},
    }
    with patch("app.services.whatsapp_service.WhatsAppService.send_whatsapp_message") as mock_send:
        mock_send.return_value = True
        res = process_message(message=msg, sender_name="Citizen", db=db)
        assert res.get("type") == "unsupported"
        assert mock_send.called
        sent_text = mock_send.call_args[1]["message_text"]
        assert "Unsupported message type" in sent_text


def test_process_message_missing_sender(db: Session):
    """Test rejection when message lacks a sender phone number."""
    msg = {"id": "wamid.no_sender", "type": "text", "text": {"body": "hello"}}
    res = process_message(message=msg, sender_name="Citizen", db=db)
    assert res.get("error") == "missing_sender"


def test_text_verification_exception_handling(db: Session):
    """Test graceful handling when verify_text raises an internal error."""
    unique_phone = f"91{uuid.uuid4().int % 10000000000:010d}"
    msg = {
        "from": unique_phone,
        "id": f"wamid.{uuid.uuid4().hex}",
        "type": "text",
        "text": {"body": "Unexpected syntax query"},
    }
    with patch("app.services.whatsapp_service.verify_text", side_effect=RuntimeError("DB query timeout")), \
         patch("app.services.whatsapp_service.WhatsAppService.send_whatsapp_message") as mock_send:
        mock_send.return_value = True
        res = process_message(message=msg, sender_name="Citizen", db=db)
        assert "error" in res
        assert mock_send.called
        sent_text = mock_send.call_args[1]["message_text"]
        assert "We couldn't verify that text statement" in sent_text


# ============================================================================
# 6. Outbound WhatsApp Cloud API Dispatch Tests
# ============================================================================

def test_send_whatsapp_message_cloud_api_success():
    """Test send_whatsapp_message posts correct JSON payload to Meta Graph API."""
    phone_id = "1316888524836995"
    token = "EAABtesttoken999"

    with patch.object(settings, "WHATSAPP_PHONE_NUMBER_ID", phone_id), \
         patch.object(settings, "WHATSAPP_ACCESS_TOKEN", token), \
         patch("httpx.Client.post") as mock_post:
        mock_post.return_value = httpx.Response(200, request=httpx.Request("POST", "http://meta.test"))

        result = send_whatsapp_message(to_number="919876543210", message_text="*Official Verdict*")
        assert result is True
        assert mock_post.called

        # Inspect call parameters
        call_url = mock_post.call_args[0][0]
        assert phone_id in call_url
        headers = mock_post.call_args[1]["headers"]
        assert headers["Authorization"] == f"Bearer {token}"
        payload = mock_post.call_args[1]["json"]
        assert payload["to"] == "919876543210"
        assert payload["type"] == "text"
        assert payload["text"]["body"] == "*Official Verdict*"


def test_send_interactive_message_cloud_api_success():
    """Test send_interactive_message posts formatted interactive reply buttons to Meta Graph API."""
    phone_id = "1316888524836995"
    token = "EAABtesttoken999"

    with patch.object(settings, "WHATSAPP_PHONE_NUMBER_ID", phone_id), \
         patch.object(settings, "WHATSAPP_ACCESS_TOKEN", token), \
         patch("httpx.Client.post") as mock_post:
        mock_post.return_value = httpx.Response(200, request=httpx.Request("POST", "http://meta.test"))

        buttons = [
            {"id": "btn_proof", "title": "How was this checked"},
            {"id": "btn_report", "title": "Report this content"},
        ]
        result = send_interactive_message(to_number="919876543210", body_text="Verdict Body", buttons=buttons)
        assert result is True
        assert mock_post.called

        payload = mock_post.call_args[1]["json"]
        assert payload["to"] == "919876543210"
        assert payload["type"] == "interactive"
        interactive_data = payload["interactive"]
        assert interactive_data["type"] == "button"
        assert interactive_data["body"]["text"] == "Verdict Body"
        assert len(interactive_data["action"]["buttons"]) == 2
        assert interactive_data["action"]["buttons"][0]["reply"]["id"] == "btn_proof"


def test_send_messages_when_unconfigured():
    """Test simulated dispatch returns True without making network calls when credentials missing."""
    with patch.object(settings, "WHATSAPP_PHONE_NUMBER_ID", ""), \
         patch.object(settings, "WHATSAPP_ACCESS_TOKEN", ""), \
         patch("httpx.Client.post") as mock_post:
        assert send_whatsapp_message("919876543210", "Test text") is True
        assert send_interactive_message("919876543210", "Body", [{"id": "b1", "title": "T1"}]) is True
        assert not mock_post.called


# ============================================================================
# 7. Rate Limiting, Retries, Deduplication, and Caching Tests
# ============================================================================

def test_per_user_rate_limiting(db: Session):
    """Test that submitting requests beyond rate limit sends rate limit notice."""
    rate_limited_phone = f"91{uuid.uuid4().int % 10000000000:010d}"

    with patch("app.services.whatsapp_service.WhatsAppService.send_whatsapp_message") as mock_send, \
         patch("app.services.whatsapp_service.WhatsAppService.send_interactive_message") as mock_send_int:
        mock_send.return_value = True
        mock_send_int.return_value = True

        # Send 10 messages (limit)
        for i in range(10):
            msg = {
                "from": rate_limited_phone,
                "id": f"wamid.rate_{i}_{uuid.uuid4().hex}",
                "type": "text",
                "text": {"body": "help"},
            }
            res = process_message(message=msg, sender_name="Citizen", db=db)
            assert res.get("type") == "help"

        # 11th message should be rate limited
        rate_limited_msg = {
            "from": rate_limited_phone,
            "id": f"wamid.rate_11_{uuid.uuid4().hex}",
            "type": "text",
            "text": {"body": "help"},
        }
        res_limit = process_message(message=rate_limited_msg, sender_name="Citizen", db=db)
        assert res_limit.get("type") == "rate_limited"
        assert mock_send.called
        last_sent = mock_send.call_args[1]["message_text"]
        assert "Rate Limit Exceeded" in last_sent


def test_retry_logic_transient_5xx():
    """Test retry logic retries transient 5xx errors and succeeds upon recovery."""
    mock_func = MagicMock()
    res_503 = httpx.Response(503, request=httpx.Request("POST", "http://meta.test"))
    res_200 = httpx.Response(200, request=httpx.Request("POST", "http://meta.test"))
    mock_func.side_effect = [res_503, res_503, res_200]

    with patch("time.sleep") as mock_sleep:
        final_res = execute_with_retry(mock_func, max_retries=3, base_delay=0.1)
        assert final_res is not None
        assert final_res.status_code == 200
        assert mock_func.call_count == 3
        assert mock_sleep.call_count == 2


def test_retry_logic_permanent_4xx_no_retry():
    """Test retry logic does NOT retry permanent 4xx client errors."""
    mock_func = MagicMock()
    res_404 = httpx.Response(404, request=httpx.Request("GET", "http://meta.test"))
    mock_func.return_value = res_404

    with patch("time.sleep") as mock_sleep:
        final_res = execute_with_retry(mock_func, max_retries=3, base_delay=0.1)
        assert final_res is not None
        assert final_res.status_code == 404
        assert mock_func.call_count == 1
        assert mock_sleep.call_count == 0


def test_message_deduplication(db: Session):
    """Test that re-delivered webhook message IDs are skipped."""
    duplicate_msg_id = f"wamid.dup_{uuid.uuid4().hex}"
    phone = f"91{uuid.uuid4().int % 10000000000:010d}"

    message = {
        "from": phone,
        "id": duplicate_msg_id,
        "type": "text",
        "text": {"body": "help"},
    }

    with patch("app.services.whatsapp_service.WhatsAppService.send_interactive_message") as mock_send_int:
        mock_send_int.return_value = True

        # First delivery -> processes normally
        res1 = process_message(message=message, sender_name="Citizen", db=db)
        assert res1.get("type") == "help"

        # Second delivery with same msg_id -> skipped as duplicate
        res2 = process_message(message=message, sender_name="Citizen", db=db)
        assert res2.get("type") == "duplicate_skipped"


def test_redis_verification_caching(db: Session):
    """Test that identical text queries retrieve cached verification results."""
    unique_text = f"Official communique {uuid.uuid4().hex}"
    phone1 = f"91{uuid.uuid4().int % 10000000000:010d}"
    phone2 = f"91{uuid.uuid4().int % 10000000000:010d}"

    msg1 = {
        "from": phone1,
        "id": f"wamid.c1_{uuid.uuid4().hex}",
        "type": "text",
        "text": {"body": unique_text},
    }

    with patch("app.services.whatsapp_service.WhatsAppService.send_interactive_message") as mock_send_int, \
         patch("app.services.whatsapp_service.verify_text") as mock_verify:
        mock_send_int.return_value = True
        mock_verify.return_value = {
            "verification_id": str(uuid.uuid4()),
            "verdict": "UNSIGNED",
            "confidence_score": 0.0,
            "evidence_bundle": {},
        }

        # First request runs verification
        res1 = process_message(message=msg1, sender_name="Citizen 1", db=db)
        assert mock_verify.call_count == 1

        # Second request with same content should hit cache
        msg2 = {
            "from": phone2,
            "id": f"wamid.c2_{uuid.uuid4().hex}",
            "type": "text",
            "text": {"body": unique_text},
        }
        res2 = process_message(message=msg2, sender_name="Citizen 2", db=db)
        assert mock_verify.call_count == 1  # Not called again
        assert res2.get("verdict") == "UNSIGNED"


def test_cache_invalidation_on_content_registration(db: Session, tmp_path):
    """Test that registering new content flushes stale verification caches."""
    # 1. Register publisher
    email = f"cache_pub_{uuid.uuid4().hex[:6]}@gov.in"
    user = register_publisher(
        db=db,
        email=email,
        password="Password123!",
        organization_name="Ministry of Health",
        organization_domain="mohfw.gov.in",
    )

    # 2. Simulate caching of an unknown media hash
    dummy_sha256 = f"abc{uuid.uuid4().hex[:61]}"
    cache_key = f"media:{dummy_sha256}"
    WhatsAppService.set_cached_verification(
        cache_key=cache_key,
        result={"verdict": "UNSIGNED", "matched_content": None},
    )
    assert WhatsAppService.get_cached_verification(cache_key) is not None

    # 3. Register a new image content
    img_bytes = generate_distinct_image()
    upload = UploadFile(filename="official_advisory.png", file=io.BytesIO(img_bytes))
    register_content(db=db, publisher=user, upload_file=upload)

    # 4. Cache should have been invalidated by register_content
    assert WhatsAppService.get_cached_verification(cache_key) is None


def test_async_webhook_post_endpoint(client):
    """Test POST /api/v1/webhook/whatsapp immediately returns 200 and triggers background processing."""
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123456",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15551234567",
                                "phone_number_id": "1316888524836995",
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "Test User"},
                                    "wa_id": "919876543210",
                                }
                            ],
                            "messages": [
                                {
                                    "from": "919876543210",
                                    "id": f"wamid.async_{uuid.uuid4().hex}",
                                    "timestamp": "1710000000",
                                    "type": "text",
                                    "text": {"body": "hello"},
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }

    with patch("app.services.whatsapp_service.WhatsAppService.send_interactive_message") as mock_send_int:
        mock_send_int.return_value = True
        response = client.post("/api/v1/webhook/whatsapp", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "EVENT_RECEIVED"
        assert mock_send_int.called


def test_handle_webhook_batch_and_caps(db: Session):
    """Test handle_webhook processing multi-message batches and respecting batch cap."""
    # Batch with 3 messages
    messages = [
        {"from": f"91987654321{i}", "id": f"wamid.batch_{i}_{uuid.uuid4().hex}", "type": "text", "text": {"body": "help"}}
        for i in range(3)
    ]
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123",
                "changes": [{"value": {"messages": messages}, "field": "messages"}],
            }
        ],
    }

    with patch("app.services.whatsapp_service.WhatsAppService.send_interactive_message") as mock_send, \
         patch("app.services.whatsapp_service.WhatsAppService.mark_message_as_read", return_value=True):
        mock_send.return_value = True
        res = handle_webhook(payload, db=db)
        assert res["status"] == "success"
        assert res["processed_count"] == 3

    # Batch exceeding MAX_BATCH_MESSAGES (25 > 20)
    oversized_msgs = [
        {"from": f"91987654321{i}", "id": f"wamid.over_{i}_{uuid.uuid4().hex}", "type": "text", "text": {"body": "help"}}
        for i in range(25)
    ]
    over_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {"id": "123", "changes": [{"value": {"messages": oversized_msgs}, "field": "messages"}]}
        ],
    }
    with patch("app.services.whatsapp_service.WhatsAppService.send_interactive_message") as mock_send, \
         patch("app.services.whatsapp_service.WhatsAppService.mark_message_as_read", return_value=True):
        mock_send.return_value = True
        res_over = handle_webhook(over_payload, db=db)
        assert res_over["processed_count"] == 20  # capped at MAX_BATCH_MESSAGES
