"""Publisher and Official Content Registration Service."""

from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

from fastapi import UploadFile
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.hash_service import (
    calculate_file_hash,
    generate_audio_fingerprint,
    generate_image_dhash,
    generate_image_phash,
    generate_video_phash,
)
from app.core.signature_service import (
    create_manifest,
    deserialize_private_key,
    generate_ed25519_keypair,
    serialize_public_key,
    sign_manifest,
)
from app.core.hash_service import add_block
from app.models.database import (
    AuditLog,
    ContentStatus,
    ContentType,
    Credential,
    CredentialStatus,
    CredentialType,
    CryptographicManifest,
    HashChainEntry,
    RegisteredContent,
    User,
)

logger = logging.getLogger(__name__)


class PublisherService:
    """Handles content registration, manifest generation, and lifecycle management."""

    @staticmethod
    def _determine_content_type(filename: str, mime_type: str) -> ContentType:
        """Infer ContentType enum from filename extension and MIME type."""
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        if ext in ["mp4", "avi", "mov", "mkv", "webm"] or "video" in mime_type:
            return ContentType.VIDEO
        if ext in ["jpg", "jpeg", "png", "webp", "gif", "bmp"] or "image" in mime_type:
            return ContentType.IMAGE
        if ext in ["mp3", "wav", "ogg", "flac", "m4a"] or "audio" in mime_type:
            return ContentType.AUDIO
        if ext == "pdf" or "pdf" in mime_type:
            return ContentType.PDF
        return ContentType.TEXT

    @classmethod
    def register_content(
        cls,
        db: Session,
        publisher: User,
        upload_file: UploadFile,
        metadata: Optional[Dict[str, Any]] = None,
        private_key_pem: Optional[str] = None,
    ) -> RegisteredContent:
        """
        Register a piece of media content into the provenance system.
        Calculates cryptographic SHA-256, perceptual hashes, signs manifest,
        and anchors to the immutable hash chain.

        Args:
            db: SQLAlchemy session.
            publisher: Authenticated User (Publisher).
            upload_file: Uploaded file from multipart form.
            metadata: Custom metadata attributes.
            private_key_pem: Optional publisher private key to sign manifest.

        Returns:
            RegisteredContent instance.
        """
        # Ensure directories exist
        upload_dir = Path(settings.PROCESSED_DIR)
        upload_dir.mkdir(parents=True, exist_ok=True)

        original_name = upload_file.filename or "content.bin"
        file_ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else "bin"
        unique_stored_name = f"{uuid.uuid4().hex}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{file_ext}"
        saved_path = upload_dir / unique_stored_name

        # Save uploaded file to disk
        try:
            with open(saved_path, "wb") as buffer:
                shutil.copyfileobj(upload_file.file, buffer)
        except Exception as e:
            logger.error("Failed to save uploaded file: %s", e)
            raise IOError(f"Could not store uploaded file: {e}") from e

        file_size = os.path.getsize(saved_path)
        mime_type = upload_file.content_type or "application/octet-stream"
        content_type = cls._determine_content_type(original_name, mime_type)

        # Step 1: Calculate SHA-256
        sha256_hash = calculate_file_hash(saved_path)

        # Check duplicate
        existing = db.execute(
            select(RegisteredContent).where(
                (RegisteredContent.sha256_hash == sha256_hash)
                & (RegisteredContent.status == ContentStatus.ACTIVE)
            )
        ).scalar_one_or_none()

        if existing:
            # Clean up duplicate file on disk
            if saved_path.exists():
                saved_path.unlink()
            raise ValueError(f"Content with identical SHA-256 ({sha256_hash}) is already registered: ID {existing.id}")

        # Step 2: Calculate Genuine Perceptual Hash
        perceptual_hash_data: Dict[str, Any] = {}
        duration_seconds: Optional[float] = None

        try:
            if content_type == ContentType.IMAGE:
                phash = generate_image_phash(saved_path)
                dhash = generate_image_dhash(saved_path)
                perceptual_hash_data = {
                    "algorithm": "pHash + dHash",
                    "phash": phash,
                    "dhash": dhash,
                }
            elif content_type == ContentType.VIDEO:
                v_phash = generate_video_phash(saved_path, fps=1.0)
                perceptual_hash_data = v_phash
                duration_seconds = v_phash.get("duration_seconds")
            elif content_type == ContentType.AUDIO:
                afp = generate_audio_fingerprint(saved_path)
                perceptual_hash_data = {
                    "algorithm": "MFCC + Chroma Fingerprint",
                    "audio_fingerprint": afp,
                }
            elif content_type == ContentType.PDF:
                perceptual_hash_data = {
                    "status": "NOT_APPLICABLE",
                    "media_type": "PDF",
                    "reason": "Perceptual hashing applies to visual and acoustic media. Document authenticity is verified via SHA-256 cryptographic hashing.",
                }
            else:  # TEXT
                perceptual_hash_data = {
                    "status": "NOT_APPLICABLE",
                    "media_type": "TEXT",
                    "reason": "Perceptual hashing applies to visual and acoustic media. Statement authenticity is verified via SHA-256 cryptographic hashing.",
                }
        except Exception as e:
            logger.warning("Perceptual hashing exception for %s: %s", saved_path, e)
            perceptual_hash_data = {
                "status": "FAILED",
                "error": str(e),
                "reason": "Could not compute media perceptual fingerprint.",
            }

        # Step 3: Find or create active Credential for publisher
        credential = db.execute(
            select(Credential).where(
                (Credential.publisher_id == publisher.id)
                & (Credential.status == CredentialStatus.ACTIVE)
            ).order_by(desc(Credential.valid_until))
        ).scalars().first()

        if not credential:
            # Create a default primary credential if missing
            now = datetime.now(timezone.utc)
            credential = Credential(
                publisher_id=publisher.id,
                credential_type=CredentialType.PRIMARY,
                status=CredentialStatus.ACTIVE,
                valid_from=now,
                valid_until=now + timedelta(days=365),
            )
            db.add(credential)
            db.flush()

        # Step 4: Create RegisteredContent record
        registered_content = RegisteredContent(
            publisher_id=publisher.id,
            credential_id=credential.id,
            content_type=content_type,
            original_filename=original_name,
            stored_filename=unique_stored_name,
            sha256_hash=sha256_hash,
            perceptual_hash=perceptual_hash_data,
            watermark_data=metadata.get("watermark") if metadata else None,
            file_size=file_size,
            mime_type=mime_type,
            duration_seconds=duration_seconds,
            status=ContentStatus.ACTIVE,
        )
        db.add(registered_content)
        db.flush()

        # Step 5: Keypair Management & Signing
        if private_key_pem:
            priv_key = deserialize_private_key(private_key_pem)
            pub_key = priv_key.public_key()
            pub_pem = serialize_public_key(pub_key)
        else:
            # Generate or use publisher keypair
            priv_key, pub_key = generate_ed25519_keypair()
            pub_pem = serialize_public_key(pub_key)
            if not publisher.public_key:
                publisher.public_key = pub_pem
                db.flush()

        # Generate standardized provenance manifest
        manifest_payload = create_manifest(
            publisher_id=publisher.id,
            content_hash=sha256_hash,
            content_type=content_type.value,
            metadata=metadata or {},
        )
        # Anchor the signing public key in the manifest for self-contained proof
        manifest_payload["publisher_public_key"] = pub_pem
        manifest_payload["publisher_name"] = publisher.organization_name
        manifest_payload["publisher_domain"] = publisher.organization_domain

        # Sign manifest
        signature = sign_manifest(manifest_payload, priv_key)

        manifest = CryptographicManifest(
            content_id=registered_content.id,
            manifest_data=manifest_payload,
            digital_signature=signature,
            signing_algorithm="Ed25519",
        )
        db.add(manifest)
        db.flush()

        # Step 6: Anchor to Hash Chain
        chain_entry = add_block(
            db=db,
            content_id=registered_content.id,
            data={
                "sha256": sha256_hash,
                "publisher_id": str(publisher.id),
                "original_filename": original_name,
                "signature": signature[:16] + "...",
            },
        )

        # Step 7: Audit Log
        audit = AuditLog(
            actor_id=publisher.id,
            action="CONTENT_REGISTER",
            details={
                "content_id": str(registered_content.id),
                "sha256": sha256_hash,
                "filename": original_name,
                "chain_block": chain_entry.id,
            },
        )
        db.add(audit)
        db.commit()
        db.refresh(registered_content)

        logger.info(
            "Registered content %s by publisher %s (Chain Block #%d)",
            registered_content.id,
            publisher.id,
            chain_entry.id,
        )
        return registered_content

    @classmethod
    def get_content(cls, db: Session, content_id: Union[str, uuid.UUID]) -> Optional[RegisteredContent]:
        """Fetch content by ID."""
        cid = uuid.UUID(str(content_id)) if isinstance(content_id, str) else content_id
        return db.execute(select(RegisteredContent).where(RegisteredContent.id == cid)).scalar_one_or_none()

    @classmethod
    def list_content(
        cls,
        db: Session,
        publisher_id: Optional[Union[str, uuid.UUID]] = None,
        content_type: Optional[ContentType] = None,
        status: Optional[ContentStatus] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[RegisteredContent], int]:
        """List content items with pagination and filters."""
        query = select(RegisteredContent)

        if publisher_id:
            pid = uuid.UUID(str(publisher_id)) if isinstance(publisher_id, str) else publisher_id
            query = query.where(RegisteredContent.publisher_id == pid)

        if content_type:
            query = query.where(RegisteredContent.content_type == content_type)

        if status:
            query = query.where(RegisteredContent.status == status)

        total_query = select(RegisteredContent)
        total = len(db.execute(total_query).scalars().all())

        items = db.execute(
            query.order_by(desc(RegisteredContent.created_at)).offset(skip).limit(limit)
        ).scalars().all()

        return list(items), total

    @classmethod
    def supersede_content(
        cls,
        db: Session,
        old_content_id: Union[str, uuid.UUID],
        new_content_id: Union[str, uuid.UUID],
        actor: User,
        reason: Optional[str] = None,
    ) -> RegisteredContent:
        """Mark old content as superseded by new content."""
        old_cid = uuid.UUID(str(old_content_id)) if isinstance(old_content_id, str) else old_content_id
        new_cid = uuid.UUID(str(new_content_id)) if isinstance(new_content_id, str) else new_content_id

        old_content = cls.get_content(db, old_cid)
        new_content = cls.get_content(db, new_cid)

        if not old_content or not new_content:
            raise ValueError("Target content item not found")

        old_content.status = ContentStatus.SUPERSEDED
        old_content.superseded_by_id = new_content.id

        audit = AuditLog(
            actor_id=actor.id,
            action="CONTENT_SUPERSEDED",
            details={
                "old_content_id": str(old_cid),
                "new_content_id": str(new_cid),
                "reason": reason or "Updated official version",
            },
        )
        db.add(audit)
        db.commit()
        db.refresh(old_content)
        return old_content

    @classmethod
    def revoke_content(
        cls,
        db: Session,
        content_id: Union[str, uuid.UUID],
        actor: User,
        reason: str,
    ) -> RegisteredContent:
        """Revoke official content status."""
        cid = uuid.UUID(str(content_id)) if isinstance(content_id, str) else content_id
        content = cls.get_content(db, cid)
        if not content:
            raise ValueError("Content not found")

        content.status = ContentStatus.REVOKED

        audit = AuditLog(
            actor_id=actor.id,
            action="CONTENT_REVOKED",
            details={"content_id": str(cid), "reason": reason},
        )
        db.add(audit)
        db.commit()
        db.refresh(content)
        return content


# Functional aliases
register_content = PublisherService.register_content
get_content = PublisherService.get_content
list_content = PublisherService.list_content
supersede_content = PublisherService.supersede_content
revoke_content = PublisherService.revoke_content
