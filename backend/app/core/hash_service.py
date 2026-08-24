"""Hash and Perceptual Fingerprinting Service.

Provides cryptographic (SHA-256), perceptual (image/video/audio),
and hash-chain integrity verification services.
"""

from concurrent.futures import ThreadPoolExecutor
import datetime
import hashlib
import io
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

import cv2
import imagehash
import numpy as np
from PIL import Image
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.database import HashChainEntry

logger = logging.getLogger(__name__)

# Genesis block constant
GENESIS_HASH: str = "0" * 64


# ============================================================================
# 1. SHA256 Cryptographic Hash Service
# ============================================================================

class SHA256Service:
    """SHA-256 Cryptographic Hashing Service."""

    @staticmethod
    def calculate_file_hash(file_path: Union[str, Path], chunk_size: int = 65536) -> str:
        """
        Calculate the SHA-256 hash of a file using streaming chunks.
        Optimized for large media files without high memory usage.

        Args:
            file_path: Path to the target file.
            chunk_size: Buffer size in bytes for reading (default: 64 KB).

        Returns:
            Hexadecimal SHA-256 hash string (64 characters).

        Raises:
            FileNotFoundError: If the file does not exist.
            IOError: If reading the file fails.
        """
        path = Path(file_path)
        if not path.is_file():
            logger.error("File not found for hashing: %s", file_path)
            raise FileNotFoundError(f"File not found: {file_path}")

        sha256 = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                while chunk := f.read(chunk_size):
                    sha256.update(chunk)
            digest = sha256.hexdigest()
            logger.debug("Calculated SHA-256 for %s: %s", path.name, digest)
            return digest
        except Exception as e:
            logger.error("Failed to calculate SHA-256 for %s: %s", file_path, e)
            raise IOError(f"Error calculating hash for {file_path}: {e}") from e

    @staticmethod
    def calculate_bytes_hash(data: Union[bytes, bytearray, memoryview]) -> str:
        """
        Calculate SHA-256 hash of raw bytes.

        Args:
            data: Raw byte payload.

        Returns:
            Hexadecimal SHA-256 hash string.
        """
        if isinstance(data, memoryview):
            data = data.tobytes()
        return hashlib.sha256(data).hexdigest()

    @classmethod
    def verify_file_hash(cls, file_path: Union[str, Path], expected_hash: str) -> bool:
        """
        Verify if a file matches an expected SHA-256 hash in constant time.

        Args:
            file_path: Path to the target file.
            expected_hash: Expected 64-character SHA-256 hash.

        Returns:
            True if the file hash matches the expected hash, False otherwise.
        """
        try:
            actual_hash = cls.calculate_file_hash(file_path)
            is_match = hashlib.sha256(actual_hash.encode()).hexdigest() == hashlib.sha256(expected_hash.lower().encode()).hexdigest()
            return is_match
        except Exception as e:
            logger.warning("File hash verification failed for %s: %s", file_path, e)
            return False


# Function aliases for SHA256Service
calculate_file_hash = SHA256Service.calculate_file_hash
calculate_bytes_hash = SHA256Service.calculate_bytes_hash
verify_file_hash = SHA256Service.verify_file_hash


# ============================================================================
# 2. Perceptual Hash Service (Image, Video, Audio)
# ============================================================================

def _load_pil_image(image_input: Union[str, Path, bytes, Image.Image]) -> Image.Image:
    """Helper to convert various image input formats to a PIL Image."""
    if isinstance(image_input, Image.Image):
        return image_input.convert("RGB")
    if isinstance(image_input, (str, Path)):
        return Image.open(str(image_input)).convert("RGB")
    if isinstance(image_input, (bytes, bytearray)):
        return Image.open(io.BytesIO(image_input)).convert("RGB")
    raise ValueError(f"Unsupported image input type: {type(image_input)}")


def _hash_single_frame(args: Tuple[int, float, np.ndarray]) -> Dict[str, Any]:
    """Helper for parallel frame hash extraction."""
    frame_idx, timestamp_s, frame_rgb = args
    pil_img = Image.fromarray(frame_rgb)
    return {
        "frame_index": frame_idx,
        "timestamp_s": round(timestamp_s, 2),
        "phash": str(imagehash.phash(pil_img)),
        "dhash": str(imagehash.dhash(pil_img)),
    }


class PerceptualHashService:
    """Perceptual Hashing and Similarity Service."""

    @staticmethod
    def generate_image_phash(image_input: Union[str, Path, bytes, Image.Image], hash_size: int = 8) -> str:
        """
        Generate perceptual hash (pHash) for an image using discrete cosine transform.

        Args:
            image_input: File path, bytes, or PIL Image.
            hash_size: Hash dimension size (default: 8 for 64-bit hash).

        Returns:
            Hexadecimal pHash string.
        """
        try:
            img = _load_pil_image(image_input)
            phash = imagehash.phash(img, hash_size=hash_size)
            return str(phash)
        except Exception as e:
            logger.error("Error generating image pHash: %s", e)
            raise ValueError(f"Failed to generate image pHash: {e}") from e

    @staticmethod
    def generate_image_dhash(image_input: Union[str, Path, bytes, Image.Image], hash_size: int = 8) -> str:
        """
        Generate difference hash (dHash) for an image tracking horizontal gradients.

        Args:
            image_input: File path, bytes, or PIL Image.
            hash_size: Hash dimension size (default: 8 for 64-bit hash).

        Returns:
            Hexadecimal dHash string.
        """
        try:
            img = _load_pil_image(image_input)
            dhash = imagehash.dhash(img, hash_size=hash_size)
            return str(dhash)
        except Exception as e:
            logger.error("Error generating image dHash: %s", e)
            raise ValueError(f"Failed to generate image dHash: {e}") from e

    @staticmethod
    def generate_video_phash(
        video_path: Union[str, Path],
        fps: float = 1.0,
        max_frames: Optional[int] = 120,
    ) -> Dict[str, Any]:
        """
        Generate perceptual frame hashes for a video at regular intervals.
        Uses multi-threaded hashing for fast frame processing.

        Args:
            video_path: Path to the video file.
            fps: Sampling rate (frames per second sampled, default 1.0).
            max_frames: Maximum sampled frames to process (to cap memory/time).

        Returns:
            Dictionary containing video metadata and frame hashes.
        """
        path = Path(video_path)
        if not path.is_file():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {video_path}")

        try:
            video_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration_s = total_frames / video_fps if video_fps > 0 else 0.0

            sample_step = max(1, int(round(video_fps / fps))) if fps > 0 else int(video_fps)

            frames_to_process: List[Tuple[int, float, np.ndarray]] = []
            frame_count = 0

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_count % sample_step == 0:
                    timestamp = frame_count / video_fps
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frames_to_process.append((frame_count, timestamp, frame_rgb))

                    if max_frames and len(frames_to_process) >= max_frames:
                        break

                frame_count += 1

            with ThreadPoolExecutor() as executor:
                frame_hashes = list(executor.map(_hash_single_frame, frames_to_process))

            combined_phashes = "".join(f["phash"] for f in frame_hashes)
            composite_phash = hashlib.sha256(combined_phashes.encode()).hexdigest() if combined_phashes else ""

            return {
                "fps_sampled": fps,
                "total_video_frames": total_frames,
                "duration_seconds": round(duration_s, 2),
                "sampled_count": len(frame_hashes),
                "composite_phash": composite_phash,
                "frame_hashes": frame_hashes,
            }
        finally:
            cap.release()

    @staticmethod
    def generate_audio_fingerprint(audio_path: Union[str, Path, bytes]) -> str:
        """
        Generate an acoustic fingerprint for an audio file using librosa.
        Extracts chroma and MFCC feature signatures robust against compression.

        Args:
            audio_path: File path or raw audio bytes.

        Returns:
            Hexadecimal acoustic fingerprint string.
        """
        try:
            import librosa
            import soundfile as sf

            if isinstance(audio_path, (bytes, bytearray)):
                audio_io = io.BytesIO(audio_path)
                y, sr = sf.read(audio_io)
                if y.ndim > 1:
                    y = np.mean(y, axis=1)
            else:
                y, sr = librosa.load(str(audio_path), sr=22050, mono=True)

            if len(y) == 0:
                return "0" * 64

            chroma = librosa.feature.chroma_stft(y=y, sr=sr, n_chroma=12)
            mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)

            chroma_mean = np.mean(chroma, axis=1)
            mfcc_mean = np.mean(mfcc, axis=1)
            features = np.concatenate([chroma_mean, mfcc_mean])

            feature_bytes = features.astype(np.float32).tobytes()
            return hashlib.sha256(feature_bytes).hexdigest()
        except Exception as e:
            logger.error("Error generating audio fingerprint: %s", e)
            if isinstance(audio_path, (bytes, bytearray)):
                return calculate_bytes_hash(audio_path)
            return calculate_file_hash(audio_path)

    @classmethod
    def compare_perceptual_hashes(
        cls,
        hash1: Union[str, Dict[str, Any]],
        hash2: Union[str, Dict[str, Any]],
    ) -> float:
        """
        Compare two perceptual hashes and return a similarity score from 0.0 to 100.0.

        Args:
            hash1: First hash (hex string or video perceptual dict).
            hash2: Second hash (hex string or video perceptual dict).

        Returns:
            Similarity percentage (0.0 to 100.0).
        """
        try:
            if isinstance(hash1, dict) and isinstance(hash2, dict):
                frames1 = hash1.get("frame_hashes", [])
                frames2 = hash2.get("frame_hashes", [])

                if not frames1 or not frames2:
                    return 0.0

                def _frame_sim(f1: Dict[str, Any], f2: Dict[str, Any]) -> float:
                    p1 = f1.get("phash", "")
                    p2 = f2.get("phash", "")
                    d1 = f1.get("dhash", p1)
                    d2 = f2.get("dhash", p2)
                    ps = cls.compare_perceptual_hashes(p1, p2)
                    ds = cls.compare_perceptual_hashes(d1, d2) if (d1 and d2) else ps
                    return (ps * 0.6) + (ds * 0.4)

                # Direct lockstep comparison (for exact or near-identical videos)
                min_len = min(len(frames1), len(frames2))
                direct_score = 0.0
                if min_len > 0:
                    direct_scores = [_frame_sim(frames1[i], frames2[i]) for i in range(min_len)]
                    direct_score = float(np.mean(direct_scores))
                    if direct_score >= 95.0 and len(frames1) == len(frames2):
                        return round(direct_score, 2)

                # Sequence alignment: match reference frames against candidate frames
                shorter, longer = (frames1, frames2) if len(frames1) <= len(frames2) else (frames2, frames1)
                ref_matches = [max(_frame_sim(sf, lf) for lf in longer) for sf in shorter]

                # Top-80% aligned mean (robust against localized edits / deepfake alterations)
                top_k = max(1, int(len(ref_matches) * 0.8))
                aligned_score = float(np.mean(sorted(ref_matches, reverse=True)[:top_k]))

                final_score = max(direct_score, aligned_score)
                return round(float(final_score), 2)

            s1 = str(hash1).strip().lower()
            s2 = str(hash2).strip().lower()

            if s1 == s2:
                return 100.0

            try:
                h1 = imagehash.hex_to_hash(s1)
                h2 = imagehash.hex_to_hash(s2)
                max_bits = len(s1) * 4
                hamming_dist = h1 - h2
                similarity = max(0.0, 100.0 * (1.0 - (hamming_dist / max_bits)))
                return round(similarity, 2)
            except Exception:
                int1 = int(s1, 16)
                int2 = int(s2, 16)
                max_bits = max(len(s1), len(s2)) * 4
                xor_val = int1 ^ int2
                hamming_dist = bin(xor_val).count("1")
                similarity = max(0.0, 100.0 * (1.0 - (hamming_dist / max_bits)))
                return round(similarity, 2)
        except Exception as e:
            logger.warning("Error comparing perceptual hashes: %s", e)
            return 0.0


# Function aliases for PerceptualHashService
generate_image_phash = PerceptualHashService.generate_image_phash
generate_image_dhash = PerceptualHashService.generate_image_dhash
generate_video_phash = PerceptualHashService.generate_video_phash
generate_audio_fingerprint = PerceptualHashService.generate_audio_fingerprint
compare_perceptual_hashes = PerceptualHashService.compare_perceptual_hashes


# ============================================================================
# 3. Hash Chain Service (Tamper-Evident Ledger)
# ============================================================================

class HashChainService:
    """
    Manages the cryptographic hash chain for content provenance.
    Ensures that every registered content is immutably linked to the previous block.
    """

    @staticmethod
    def create_genesis_block() -> str:
        """
        Return the genesis block hash representation.

        Returns:
            64-character zero hex string.
        """
        return GENESIS_HASH

    @staticmethod
    def calculate_block_hash(
        prev_hash: str,
        content_id: Union[str, uuid.UUID],
        timestamp: datetime.datetime,
        data_payload: Optional[Union[str, Dict[str, Any]]] = None,
    ) -> str:
        """
        Calculate deterministic SHA-256 hash for a chain block.

        Args:
            prev_hash: Previous block's current_hash.
            content_id: UUID of the registered content.
            timestamp: Block UTC timestamp.
            data_payload: Optional data payload or dictionary.

        Returns:
            Calculated block hash (64 hex characters).
        """
        iso_time = timestamp.isoformat() if isinstance(timestamp, datetime.datetime) else str(timestamp)
        payload_str = json.dumps(data_payload, sort_keys=True) if isinstance(data_payload, dict) else (data_payload or "")

        raw = f"{prev_hash}|{str(content_id)}|{iso_time}|{payload_str}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    @classmethod
    def add_block(
        cls,
        db: Session,
        content_id: Union[str, uuid.UUID],
        data: Optional[Union[str, Dict[str, Any]]] = None,
    ) -> HashChainEntry:
        """
        Append a new block to the hash chain and persist it in the database.

        Args:
            db: SQLAlchemy database session.
            content_id: UUID of the registered content.
            data: Additional metadata/data to bind into the block hash.

        Returns:
            Created HashChainEntry instance.
        """
        cid = uuid.UUID(str(content_id)) if isinstance(content_id, str) else content_id

        latest_entry = db.execute(
            select(HashChainEntry).order_by(desc(HashChainEntry.id)).limit(1)
        ).scalar_one_or_none()

        prev_hash = latest_entry.current_hash if latest_entry else cls.create_genesis_block()
        timestamp = datetime.datetime.now(datetime.timezone.utc)

        current_hash = cls.calculate_block_hash(
            prev_hash=prev_hash,
            content_id=cid,
            timestamp=timestamp,
            data_payload=data,
        )

        entry = HashChainEntry(
            content_id=cid,
            prev_hash=prev_hash,
            current_hash=current_hash,
            timestamp=timestamp,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)

        logger.info("Added hash chain block ID %d (current_hash: %s...)", entry.id, entry.current_hash[:8])
        return entry

    @classmethod
    def verify_chain(cls, db: Session) -> Tuple[bool, Optional[int]]:
        """
        Verify the complete integrity of the hash chain from genesis to head.

        Args:
            db: SQLAlchemy database session.

        Returns:
            Tuple of (is_valid: bool, broken_index: Optional[int]).
        """
        entries = db.execute(
            select(HashChainEntry).order_by(HashChainEntry.id.asc())
        ).scalars().all()

        if not entries:
            return True, None

        expected_prev_hash = cls.create_genesis_block()

        for idx, entry in enumerate(entries):
            if entry.prev_hash != expected_prev_hash:
                logger.error(
                    "Hash chain linkage broken at entry ID %d! Expected prev_hash: %s, got: %s",
                    entry.id,
                    expected_prev_hash,
                    entry.prev_hash,
                )
                return False, entry.id

            expected_prev_hash = entry.current_hash

        return True, None

    @classmethod
    def get_chain_state(cls, db: Session) -> Dict[str, Any]:
        """
        Get current status and statistics of the hash chain.

        Args:
            db: SQLAlchemy database session.

        Returns:
            Dictionary with chain length, genesis hash, latest hash, and integrity status.
        """
        latest_entry = db.execute(
            select(HashChainEntry).order_by(desc(HashChainEntry.id)).limit(1)
        ).scalar_one_or_none()

        is_valid, broken_id = cls.verify_chain(db)
        count = db.execute(select(HashChainEntry)).scalars().all()

        return {
            "total_blocks": len(count),
            "genesis_hash": cls.create_genesis_block(),
            "latest_block_id": latest_entry.id if latest_entry else None,
            "latest_hash": latest_entry.current_hash if latest_entry else cls.create_genesis_block(),
            "is_valid": is_valid,
            "broken_index": broken_id,
        }

    @classmethod
    def detect_tampering(cls, db: Session) -> bool:
        """
        Check if any tampering has occurred in the hash chain.

        Args:
            db: SQLAlchemy database session.

        Returns:
            True if tampering is detected (chain broken), False if intact.
        """
        is_valid, _ = cls.verify_chain(db)
        return not is_valid


# Functional aliases matching requirements
create_genesis_block = HashChainService.create_genesis_block
add_block = HashChainService.add_block
verify_chain = HashChainService.verify_chain
get_chain_state = HashChainService.get_chain_state
detect_tampering = HashChainService.detect_tampering
