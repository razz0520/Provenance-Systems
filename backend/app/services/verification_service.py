"""Content Verification Service for WhatsApp & Citizen Web API."""

from datetime import datetime, timezone
import io
import json
import logging
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.hash_service import (
    calculate_bytes_hash,
    calculate_file_hash,
    compare_perceptual_hashes,
    generate_audio_fingerprint,
    generate_image_dhash,
    generate_image_phash,
    generate_video_phash,
)
from app.core.signature_service import verify_signature
from app.models.database import (
    ContentStatus,
    ContentType,
    RegisteredContent,
    User,
    VerificationAttempt,
    VerificationVerdict,
)

logger = logging.getLogger(__name__)


class VerificationService:
    """Core verification engine matching incoming media against the provenance ledger."""

    @classmethod
    def verify_file(
        cls,
        db: Session,
        upload_file: Union[UploadFile, bytes, str, Path],
        filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Verify an uploaded file against the registered provenance database.

        Args:
            db: SQLAlchemy session.
            upload_file: UploadFile, raw bytes, or local file path.
            filename: Original filename.

        Returns:
            Dictionary containing verification verdict, confidence score, and evidence bundle.
        """
        start_time = time.perf_counter()

        temp_file_path: Optional[str] = None
        orig_name = filename or "sample.bin"

        if hasattr(upload_file, "file"):
            orig_name = getattr(upload_file, "filename", None) or orig_name
            ext = orig_name.rsplit(".", 1)[-1].lower() if "." in orig_name else "bin"
            with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
                if hasattr(upload_file.file, "seek"):
                    upload_file.file.seek(0)
                content_bytes = upload_file.file.read()
                tmp.write(content_bytes)
                temp_file_path = tmp.name
        elif isinstance(upload_file, (bytes, bytearray)):
            ext = orig_name.rsplit(".", 1)[-1].lower() if "." in orig_name else "bin"
            with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
                tmp.write(upload_file)
                temp_file_path = tmp.name
        elif isinstance(upload_file, (str, Path)):
            temp_file_path = str(upload_file)
        else:
            raise ValueError(f"Unsupported file type for verification: {type(upload_file)}")

        try:
            # Step 1: Calculate SHA-256 of submitted file
            submitted_hash = calculate_file_hash(temp_file_path)

            # Step 2: Check Exact SHA-256 Match
            matched_content = db.execute(
                select(RegisteredContent).where(RegisteredContent.sha256_hash == submitted_hash)
            ).scalar_one_or_none()

            evidence_bundle: Dict[str, Any] = {
                "match_type": "NONE",
                "sha256_submitted": submitted_hash,
                "matched_hash": None,
                "similarity_score": 0.0,
                "publisher_name": None,
                "publisher_domain": None,
                "publisher_public_key": None,
                "digital_signature": None,
                "signature_valid": False,
                "manifest_valid": False,
                "chain_block_id": None,
                "chain_integrity": False,
                "content_metadata": None,
            }

            verdict: VerificationVerdict = VerificationVerdict.UNSIGNED
            confidence_score = 0.0

            if matched_content:
                publisher = matched_content.publisher
                manifest = matched_content.manifest
                chain_entry = matched_content.hash_chain_entry

                evidence_bundle["match_type"] = "EXACT_SHA256"
                evidence_bundle["matched_hash"] = matched_content.sha256_hash
                evidence_bundle["similarity_score"] = 100.0
                evidence_bundle["publisher_name"] = publisher.organization_name if publisher else None
                evidence_bundle["publisher_domain"] = publisher.organization_domain if publisher else None
                evidence_bundle["publisher_public_key"] = publisher.public_key if publisher else None
                evidence_bundle["chain_block_id"] = chain_entry.id if chain_entry else None
                evidence_bundle["chain_integrity"] = bool(chain_entry is not None)

                # Verify digital signature on manifest
                sig_valid = False
                if manifest and publisher and publisher.public_key:
                    sig_valid = verify_signature(
                        manifest_dict=manifest.manifest_data,
                        signature=manifest.digital_signature,
                        public_key=publisher.public_key,
                    )
                    evidence_bundle["digital_signature"] = manifest.digital_signature
                    evidence_bundle["signature_valid"] = sig_valid
                    evidence_bundle["manifest_valid"] = True
                    evidence_bundle["content_metadata"] = manifest.manifest_data.get("metadata", {})

                # Determine verdict based on status
                if matched_content.status == ContentStatus.ACTIVE:
                    if sig_valid or manifest is not None:
                        verdict = VerificationVerdict.VERIFIED
                        confidence_score = 1.0
                    else:
                        verdict = VerificationVerdict.PROVEN_INVALID
                        confidence_score = 0.85
                elif matched_content.status == ContentStatus.SUPERSEDED:
                    verdict = VerificationVerdict.VERIFIED
                    confidence_score = 0.95
                    evidence_bundle["notice"] = "Content is authentic but has been superseded by an updated version."
                    evidence_bundle["superseded_by_id"] = str(matched_content.superseded_by_id)
                elif matched_content.status == ContentStatus.REVOKED:
                    verdict = VerificationVerdict.PROVEN_INVALID
                    confidence_score = 1.0
                    evidence_bundle["notice"] = "Content was officially revoked by the publishing authority."

            else:
                # Step 3: Perceptual Hash / Near-Duplicate Fuzzy Matching
                ext = orig_name.rsplit(".", 1)[-1].lower() if "." in orig_name else ""
                perceptual_candidates = db.execute(
                    select(RegisteredContent).where(RegisteredContent.status == ContentStatus.ACTIVE)
                ).scalars().all()

                best_match: Optional[RegisteredContent] = None
                best_score = 0.0

                for candidate in perceptual_candidates:
                    cand_phash = candidate.perceptual_hash
                    if not cand_phash:
                        continue

                    # Compare image hashes
                    if candidate.content_type == ContentType.IMAGE and ext in ["jpg", "jpeg", "png", "webp"]:
                        try:
                            sub_phash = generate_image_phash(temp_file_path)
                            cand_phash_val = cand_phash.get("phash", "")
                            if cand_phash_val:
                                sim = compare_perceptual_hashes(sub_phash, cand_phash_val)
                                if sim > best_score:
                                    best_score = sim
                                    best_match = candidate
                        except Exception:
                            pass

                    # Compare video hashes
                    elif candidate.content_type == ContentType.VIDEO and ext in ["mp4", "avi", "mov", "mkv"]:
                        try:
                            sub_v_phash = generate_video_phash(temp_file_path, fps=1.0)
                            sim = compare_perceptual_hashes(sub_v_phash, cand_phash)
                            if sim > best_score:
                                best_score = sim
                                best_match = candidate
                        except Exception:
                            pass

                    # Compare audio fingerprints
                    elif candidate.content_type == ContentType.AUDIO and ext in ["mp3", "wav", "ogg", "m4a"]:
                        try:
                            sub_afp = generate_audio_fingerprint(temp_file_path)
                            cand_afp = cand_phash.get("audio_fingerprint", "")
                            if cand_afp:
                                sim = compare_perceptual_hashes(sub_afp, cand_afp)
                                if sim > best_score:
                                    best_score = sim
                                    best_match = candidate
                        except Exception:
                            pass

                # Evaluate perceptual similarity thresholds
                if best_match and best_score >= 70.0:
                    matched_content = best_match
                    evidence_bundle["match_type"] = "PERCEPTUAL_SIMILARITY"
                    evidence_bundle["matched_hash"] = best_match.sha256_hash
                    evidence_bundle["similarity_score"] = best_score
                    evidence_bundle["publisher_name"] = best_match.publisher.organization_name if best_match.publisher else None
                    evidence_bundle["publisher_domain"] = best_match.publisher.organization_domain if best_match.publisher else None

                    if best_score >= 95.0:
                        verdict = VerificationVerdict.VERIFIED
                        confidence_score = round(best_score / 100.0, 2)
                        evidence_bundle["notice"] = "Matches authentic registered content with minor format compression."
                    else:
                        verdict = VerificationVerdict.SUSPICIOUS
                        confidence_score = round(best_score / 100.0, 2)
                        evidence_bundle["notice"] = (
                            f"Content shows {best_score}% visual/acoustic similarity to registered content "
                            f"(ID: {best_match.id}) but has alterations/modifications."
                        )
                else:
                    verdict = VerificationVerdict.UNSIGNED
                    confidence_score = 0.0
                    evidence_bundle["notice"] = "No matching official provenance record found in the government registry."

            elapsed_ms = max(1, int((time.perf_counter() - start_time) * 1000))

            # Step 4: Persist Verification Attempt Log
            attempt = VerificationAttempt(
                submitted_hash=submitted_hash,
                matched_content_id=matched_content.id if matched_content else None,
                verdict=verdict,
                evidence_bundle=evidence_bundle,
                confidence_score=confidence_score,
                verification_time_ms=elapsed_ms,
            )
            db.add(attempt)
            db.commit()
            db.refresh(attempt)

            return {
                "verification_id": str(attempt.id),
                "submitted_hash": submitted_hash,
                "verdict": verdict.value,
                "confidence_score": confidence_score,
                "verification_time_ms": elapsed_ms,
                "matched_content": matched_content.to_dict() if matched_content else None,
                "evidence_bundle": evidence_bundle,
                "created_at": attempt.created_at.isoformat(),
            }

        finally:
            if temp_file_path and os.path.exists(temp_file_path) and "tmp" in temp_file_path:
                try:
                    os.unlink(temp_file_path)
                except Exception:
                    pass

    @classmethod
    def verify_text(cls, db: Session, text_content: str) -> Dict[str, Any]:
        """
        Verify raw text content against the provenance database.

        Args:
            db: SQLAlchemy session.
            text_content: Raw text string.

        Returns:
            Verification result dictionary.
        """
        raw_bytes = text_content.strip().encode("utf-8")
        return cls.verify_file(db, raw_bytes, filename="statement.txt")

    @classmethod
    def get_verification_result(
        cls,
        db: Session,
        verification_id: Union[str, uuid.UUID],
    ) -> Optional[Dict[str, Any]]:
        """Retrieve historical verification attempt by ID."""
        vid = uuid.UUID(str(verification_id)) if isinstance(verification_id, str) else verification_id
        attempt = db.execute(
            select(VerificationAttempt).where(VerificationAttempt.id == vid)
        ).scalar_one_or_none()

        if not attempt:
            return None

        matched_content = attempt.matched_content
        return {
            "verification_id": str(attempt.id),
            "submitted_hash": attempt.submitted_hash,
            "verdict": attempt.verdict.value,
            "confidence_score": attempt.confidence_score,
            "verification_time_ms": attempt.verification_time_ms,
            "matched_content": matched_content.to_dict() if matched_content else None,
            "evidence_bundle": attempt.evidence_bundle,
            "created_at": attempt.created_at.isoformat(),
        }


# Functional aliases
verify_file = VerificationService.verify_file
verify_text = VerificationService.verify_text
get_verification_result = VerificationService.get_verification_result
