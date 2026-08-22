"""Digital Signature and Cryptographic Manifest Service.

Implements Ed25519 keypair management, digital signatures,
and cryptographic manifest creation, serialization, and validation.
"""

import base64
import datetime
import json
import logging
from typing import Any, Dict, Optional, Tuple, Union
import uuid

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.database import User

logger = logging.getLogger(__name__)


# ============================================================================
# 1. Key Management (Ed25519)
# ============================================================================

class KeyManager:
    """Ed25519 Keypair Management and Serialization Service."""

    @staticmethod
    def generate_ed25519_keypair() -> Tuple[ed25519.Ed25519PrivateKey, ed25519.Ed25519PublicKey]:
        """Generate a new Ed25519 asymmetric keypair."""
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        return private_key, public_key

    @staticmethod
    def serialize_private_key(
        private_key: ed25519.Ed25519PrivateKey,
        password: Optional[str] = None,
    ) -> str:
        """Serialize an Ed25519 private key to PEM format string (PKCS8)."""
        encryption = (
            serialization.BestAvailableEncryption(password.encode("utf-8"))
            if password
            else serialization.NoEncryption()
        )
        pem_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=encryption,
        )
        return pem_bytes.decode("utf-8")

    @staticmethod
    def serialize_public_key(public_key: ed25519.Ed25519PublicKey) -> str:
        """Serialize an Ed25519 public key to PEM format string (SubjectPublicKeyInfo)."""
        pem_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return pem_bytes.decode("utf-8")

    @staticmethod
    def deserialize_private_key(
        pem_data: Union[str, bytes],
        password: Optional[str] = None,
    ) -> ed25519.Ed25519PrivateKey:
        """Deserialize an Ed25519 private key from PEM format."""
        data = pem_data.encode("utf-8") if isinstance(pem_data, str) else pem_data
        pwd_bytes = password.encode("utf-8") if password else None
        key = serialization.load_pem_private_key(data, password=pwd_bytes)
        if not isinstance(key, ed25519.Ed25519PrivateKey):
            raise ValueError(f"Expected Ed25519 private key, got {type(key)}")
        return key

    @staticmethod
    def deserialize_public_key(pem_data: Union[str, bytes]) -> ed25519.Ed25519PublicKey:
        """Deserialize an Ed25519 public key from PEM format (or raw Base64/Hex)."""
        data = pem_data.encode("utf-8") if isinstance(pem_data, str) else pem_data
        if b"BEGIN PUBLIC KEY" in data:
            key = serialization.load_pem_public_key(data)
            if not isinstance(key, ed25519.Ed25519PublicKey):
                raise ValueError(f"Expected Ed25519 public key, got {type(key)}")
            return key

        try:
            raw_bytes = base64.b64decode(data) if len(data) == 44 else bytes.fromhex(data.decode("utf-8"))
            if len(raw_bytes) == 32:
                return ed25519.Ed25519PublicKey.from_public_bytes(raw_bytes)
        except Exception:
            pass

        raise ValueError("Could not parse public key from provided data format")

    @classmethod
    def serialize_keys(
        cls,
        private_key: ed25519.Ed25519PrivateKey,
        public_key: ed25519.Ed25519PublicKey,
        password: Optional[str] = None,
    ) -> Tuple[str, str]:
        """Serialize both keys in a keypair to PEM strings."""
        return cls.serialize_private_key(private_key, password), cls.serialize_public_key(public_key)

    @classmethod
    def deserialize_keys(
        cls,
        private_pem: str,
        public_pem: str,
        password: Optional[str] = None,
    ) -> Tuple[ed25519.Ed25519PrivateKey, ed25519.Ed25519PublicKey]:
        """Deserialize both PEM strings into key objects."""
        return cls.deserialize_private_key(private_pem, password), cls.deserialize_public_key(public_pem)

    @staticmethod
    def store_keypair(
        db: Session,
        publisher_id: Union[str, uuid.UUID],
        public_key_pem: str,
    ) -> bool:
        """Store or update a publisher's public key in the database."""
        pid = uuid.UUID(str(publisher_id)) if isinstance(publisher_id, str) else publisher_id
        user = db.execute(select(User).where(User.id == pid)).scalar_one_or_none()
        if not user:
            logger.warning("User %s not found for storing public key", publisher_id)
            return False

        user.public_key = public_key_pem
        db.commit()
        logger.info("Stored Ed25519 public key for user %s", publisher_id)
        return True

    @staticmethod
    def get_public_key(db: Session, publisher_id: Union[str, uuid.UUID]) -> Optional[str]:
        """Retrieve a publisher's public key from the database."""
        pid = uuid.UUID(str(publisher_id)) if isinstance(publisher_id, str) else publisher_id
        user = db.execute(select(User).where(User.id == pid)).scalar_one_or_none()
        return user.public_key if user else None


# Functional aliases for KeyManager
generate_ed25519_keypair = KeyManager.generate_ed25519_keypair
serialize_private_key = KeyManager.serialize_private_key
serialize_public_key = KeyManager.serialize_public_key
deserialize_private_key = KeyManager.deserialize_private_key
deserialize_public_key = KeyManager.deserialize_public_key
serialize_keys = KeyManager.serialize_keys
deserialize_keys = KeyManager.deserialize_keys
store_keypair = KeyManager.store_keypair
get_public_key = KeyManager.get_public_key


# ============================================================================
# 2. Digital Signatures (Ed25519)
# ============================================================================

class SignatureService:
    """Digital Signature Signing and Verification Service."""

    @staticmethod
    def sign_data(
        data: Union[bytes, str],
        private_key: Union[ed25519.Ed25519PrivateKey, str, bytes],
    ) -> str:
        """Sign arbitrary data using an Ed25519 private key."""
        if not isinstance(private_key, ed25519.Ed25519PrivateKey):
            private_key = KeyManager.deserialize_private_key(private_key)

        payload = data.encode("utf-8") if isinstance(data, str) else data
        signature_bytes = private_key.sign(payload)
        return base64.b64encode(signature_bytes).decode("utf-8")

    @staticmethod
    def verify_data_signature(
        data: Union[bytes, str],
        signature: Union[str, bytes],
        public_key: Union[ed25519.Ed25519PublicKey, str, bytes],
    ) -> bool:
        """Verify an Ed25519 digital signature against data."""
        try:
            if not isinstance(public_key, ed25519.Ed25519PublicKey):
                public_key = KeyManager.deserialize_public_key(public_key)

            payload = data.encode("utf-8") if isinstance(data, str) else data
            sig_bytes = base64.b64decode(signature) if isinstance(signature, str) else signature
            public_key.verify(sig_bytes, payload)
            return True
        except (InvalidSignature, ValueError, Exception) as e:
            logger.debug("Signature verification failed: %s", e)
            return False

    @classmethod
    def sign_manifest(
        cls,
        manifest_dict: Dict[str, Any],
        private_key: Union[ed25519.Ed25519PrivateKey, str, bytes],
    ) -> str:
        """Deterministically serialize and sign a manifest dictionary."""
        canonical_bytes = ManifestService.serialize_manifest(manifest_dict)
        return cls.sign_data(canonical_bytes, private_key)

    @classmethod
    def verify_signature(
        cls,
        manifest_dict: Dict[str, Any],
        signature: str,
        public_key: Union[ed25519.Ed25519PublicKey, str, bytes],
    ) -> bool:
        """Verify signature against a canonicalized manifest dictionary."""
        canonical_bytes = ManifestService.serialize_manifest(manifest_dict)
        return cls.verify_data_signature(canonical_bytes, signature, public_key)


# Functional aliases for SignatureService
sign_data = SignatureService.sign_data
verify_data_signature = SignatureService.verify_data_signature
sign_manifest = SignatureService.sign_manifest
verify_signature = SignatureService.verify_signature


# ============================================================================
# 3. Manifest Service
# ============================================================================

class ManifestService:
    """Provenance Manifest Management Service."""

    @staticmethod
    def create_manifest(
        publisher_id: Union[str, uuid.UUID],
        content_hash: str,
        content_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a standardized cryptographic manifest dictionary."""
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return {
            "manifest_version": "1.0",
            "publisher_id": str(publisher_id),
            "content_hash": content_hash.lower(),
            "content_type": content_type.upper(),
            "timestamp": now_iso,
            "signing_algorithm": "Ed25519",
            "metadata": metadata or {},
        }

    @staticmethod
    def serialize_manifest(manifest: Dict[str, Any]) -> bytes:
        """Serialize manifest to deterministic canonical JSON bytes."""
        return json.dumps(
            manifest,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")

    @staticmethod
    def deserialize_manifest(data: Union[bytes, str]) -> Dict[str, Any]:
        """Deserialize JSON byte string or string into a manifest dictionary."""
        try:
            raw_str = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else data
            return json.loads(raw_str)
        except Exception as e:
            logger.error("Failed to deserialize manifest: %s", e)
            raise ValueError(f"Invalid manifest data: {e}") from e

    @staticmethod
    def validate_manifest(manifest: Dict[str, Any]) -> bool:
        """Validate that a manifest contains all required fields and schema constraints."""
        if not isinstance(manifest, dict):
            return False

        required_keys = [
            "manifest_version",
            "publisher_id",
            "content_hash",
            "content_type",
            "timestamp",
            "signing_algorithm",
        ]

        for key in required_keys:
            if key not in manifest or not manifest[key]:
                logger.debug("Manifest validation missing key: %s", key)
                return False

        content_hash = str(manifest["content_hash"]).strip()
        if len(content_hash) != 64 or not all(c in "0123456789abcdefABCDEF" for c in content_hash):
            logger.debug("Invalid content_hash format in manifest: %s", content_hash)
            return False

        if manifest.get("signing_algorithm") != "Ed25519":
            logger.debug("Unsupported algorithm in manifest: %s", manifest.get("signing_algorithm"))
            return False

        return True


# Functional aliases for ManifestService
create_manifest = ManifestService.create_manifest
serialize_manifest = ManifestService.serialize_manifest
deserialize_manifest = ManifestService.deserialize_manifest
validate_manifest = ManifestService.validate_manifest
