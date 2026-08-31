# Exhaustive Architectural Inspection
## Deepfake-Resistant Government Provenance & Verification System

> **READ-ONLY AUDIT** — No speculation. Every claim is cited by exact file path and line numbers.

---

## SECTION 1 — SYSTEM FOUNDATION

### 1.1 Runtime Stack

| Layer | Technology | Version pinned in |
|---|---|---|
| Language | Python 3.x (CPython) | Implicit |
| Web Framework | FastAPI 0.104.1 | `backend/requirements.txt:2` |
| ASGI Server | Uvicorn[standard] 0.24.0 | `backend/requirements.txt:3` |
| ORM | SQLAlchemy 2.0.23 | `backend/requirements.txt:7` |
| DB Driver | psycopg2-binary 2.9.9 | `backend/requirements.txt:8` |
| Migrations | Alembic 1.12.1 | `backend/requirements.txt:9` |
| Cache / Session | Redis 5.0.1 | `backend/requirements.txt:10` |

### 1.2 Application Entry Point

File: `backend/app/main.py`

- **FastAPI instance** created at line 70 with title, version, `docs_url="/docs"`, `openapi_url="/api/v1/openapi.json"`.
- **Lifespan** (`asynccontextmanager`) at lines 48-66: creates `UPLOAD_DIR`, `TEMP_DIR`, `PROCESSED_DIR` on startup, calls `init_db()`, and logs shutdown.
- **CORS** middleware at lines 91-98: permits origins from `settings.BACKEND_CORS_ORIGINS` (default: `["http://localhost:3000","http://localhost:8000"]`) — `backend/app/config.py:47`.
- **Security + Timing middleware** (async, inline) at lines 102-135: generates/validates `X-Request-ID` via `set_current_request_id()`, records latency, injects `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy`, `Permissions-Policy`, `Strict-Transport-Security`, and `Content-Security-Policy` headers on every response.
- **Exception handlers** registered at lines 142-240 for: `HTTPException`, `RequestValidationError`, `ValueError`, `ProcessingTimeoutError`, `SQLAlchemyError`, and a global `Exception` fallback — all return structured JSON envelopes with `request_id`.
- **Static file mount** at line 250: `uploads/` directory served under `/uploads`.
- **Router mounting**: system router at line 253, then `api_v1_router` under `/api/v1` at line 256.

### 1.3 Database Connection Pool

File: `backend/app/database.py`

```python
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
    echo=False,
)
```

Lines 11-18. Pool of 10 persistent connections, overflow up to 20, recycled every 3600 seconds, with `pool_pre_ping=True` to detect stale connections.

`SessionLocal` factory at lines 21-26: `autocommit=False`, `autoflush=False`, `expire_on_commit=False`.

`init_db()` (line 44) calls `Base.metadata.create_all(bind=engine)` — creates all tables defined in the ORM models. **No Alembic migration scripts are present** in `backend/alembic/versions/` (directory is empty).

### 1.4 Configuration System

File: `backend/app/config.py` — Pydantic `BaseSettings` class, lines 14-72.

All secrets/parameters are loaded from `.env` files in a priority chain (init → dotenv → env-file → file secrets) via `settings_customise_sources` at lines 63-72.

Key defaults (overridden by `.env`):

| Key | Default | Line |
|---|---|---|
| `DATABASE_URL` | `postgresql://provenance:provenance123@localhost:5432/provenance_db` | 16 |
| `REDIS_URL` | `redis://localhost:6379/0` | 17 |
| `SECRET_KEY` | placeholder — must be replaced | 20 |
| `JWT_ALGORITHM` | `HS256` | 21 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 30 | 22 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | 7 | 23 |
| `MAX_UPLOAD_SIZE` | 16,777,216 bytes (16 MB) | 38 |
| `MEDIA_PROCESSING_TIMEOUT_SECONDS` | 120 | 39 |
| `UPLOAD_DIR` | `uploads` | 41 |
| `TEMP_DIR` | `uploads/temp` | 42 |
| `PROCESSED_DIR` | `uploads/processed` | 43 |

---

## SECTION 2 — DATABASE SCHEMA

File: `backend/app/models/database.py`

All models extend `Base(DeclarativeBase)` (line 28). Uses SQLAlchemy 2.0 `Mapped` / `mapped_column` API.

### 2.1 Enumerations (lines 37-73)

| Enum | Values |
|---|---|
| `UserRole` | `ADMIN`, `PUBLISHER`, `VIEWER` |
| `CredentialType` | `PRIMARY`, `SECONDARY` |
| `CredentialStatus` | `ACTIVE`, `SUSPENDED`, `REVOKED`, `EXPIRED` |
| `ContentType` | `VIDEO`, `IMAGE`, `AUDIO`, `PDF`, `TEXT` |
| `ContentStatus` | `ACTIVE`, `SUPERSEDED`, `REVOKED` |
| `VerificationVerdict` | `VERIFIED`, `SUSPICIOUS`, `UNSIGNED`, `PROVEN_INVALID` |

### 2.2 Table: `users` (lines 100-260)

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | `default=uuid.uuid4` |
| `email` | String(255) | UNIQUE, NOT NULL, INDEX |
| `password_hash` | String(255) | Nullable |
| `google_id` | String(255) | UNIQUE, nullable |
| `google_email` | String(255) | Nullable |
| `role` | Enum(UserRole) | NOT NULL, default=VIEWER |
| `organization_name` | String(255) | NOT NULL |
| `organization_domain` | String(255) | NOT NULL, INDEX |
| `department` | String(255) | Nullable |
| `designation` | String(255) | Nullable |
| `public_key` | Text | Nullable — stores Ed25519 PEM |
| `is_active` | Boolean | NOT NULL, default=True |
| `is_verified` | Boolean | NOT NULL, default=False |
| `mfa_enabled` | Boolean | NOT NULL, default=False |
| `mfa_secret` | String(255) | Nullable — TOTP base32 secret |
| `last_login_at` | DateTime(tz) | Nullable |
| `last_login_ip` | String(45) | Nullable |
| `login_count` | Integer | NOT NULL, default=0 |
| `created_at` | DateTime(tz) | `server_default=func.now()` |
| `updated_at` | DateTime(tz) | `server_default=func.now()`, `onupdate=utc_now` |

Composite index: `idx_users_org_domain_role` on (`organization_domain`, `role`) — line 225.

Relationships: `credentials` (cascade all/delete-orphan), `registered_contents` (cascade all/delete-orphan), `audit_logs` (passive_deletes).

### 2.3 Table: `credentials` (lines 267-358)

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | `default=uuid.uuid4` |
| `publisher_id` | UUID (FK -> `users.id` ON DELETE CASCADE) | NOT NULL, INDEX |
| `credential_type` | Enum(CredentialType) | NOT NULL, default=PRIMARY |
| `status` | Enum(CredentialStatus) | NOT NULL, default=ACTIVE, INDEX |
| `valid_from` | DateTime(tz) | NOT NULL |
| `valid_until` | DateTime(tz) | NOT NULL |
| `revoked_at` | DateTime(tz) | Nullable |
| `revocation_reason` | Text | Nullable |
| `created_at` | DateTime(tz) | `server_default=func.now()` |

Composite indexes: `idx_credentials_publisher_status`, `idx_credentials_validity` — lines 336-337.

### 2.4 Table: `registered_contents` (lines 366-527)

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | `default=uuid.uuid4` |
| `publisher_id` | UUID (FK -> `users.id` ON DELETE CASCADE) | NOT NULL, INDEX |
| `credential_id` | UUID (FK -> `credentials.id` ON DELETE RESTRICT) | NOT NULL, INDEX |
| `content_type` | Enum(ContentType) | NOT NULL, INDEX |
| `original_filename` | String(255) | NOT NULL |
| `stored_filename` | String(255) | NOT NULL |
| `sha256_hash` | String(64) | NOT NULL, INDEX |
| `perceptual_hash` | JSON | NOT NULL |
| `watermark_data` | JSON | Nullable |
| `file_size` | BigInteger | NOT NULL |
| `mime_type` | String(100) | NOT NULL |
| `duration_seconds` | Float | Nullable |
| `status` | Enum(ContentStatus) | NOT NULL, default=ACTIVE, INDEX |
| `superseded_by_id` | UUID (FK -> self ON DELETE SET NULL) | Nullable, INDEX |
| `created_at` | DateTime(tz) | NOT NULL, INDEX |
| `updated_at` | DateTime(tz) | `onupdate=utc_now` |

`credential_id` FK uses `ON DELETE RESTRICT` (line 382) — prevents credential deletion if content references it.

Self-referential relationship `superseded_by` / `superseded_contents` — lines 468-473.

Composite indexes: `idx_registered_content_sha256`, `idx_registered_content_status_type`, `idx_registered_content_pub_status` — lines 495-497.

### 2.5 Table: `cryptographic_manifests` (lines 534-590)

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | `default=uuid.uuid4` |
| `content_id` | UUID (FK -> `registered_contents.id` ON DELETE CASCADE) | UNIQUE, NOT NULL, INDEX |
| `manifest_data` | JSON | NOT NULL |
| `digital_signature` | Text | NOT NULL |
| `signing_algorithm` | String(50) | NOT NULL, default=`"Ed25519"` |
| `created_at` | DateTime(tz) | NOT NULL |

One-to-one relationship with `RegisteredContent` via `uselist=False` — line 477.

### 2.6 Table: `hash_chain_entries` (lines 597-658)

| Column | Type | Constraints |
|---|---|---|
| `id` | Integer (PK) | `autoincrement=True` — monotonic sequential index |
| `content_id` | UUID (FK -> `registered_contents.id` ON DELETE CASCADE) | UNIQUE, NOT NULL, INDEX |
| `prev_hash` | String(64) | NOT NULL, INDEX |
| `current_hash` | String(64) | NOT NULL, INDEX |
| `timestamp` | DateTime(tz) | NOT NULL |
| `created_at` | DateTime(tz) | NOT NULL |

Composite index: `idx_hash_chain_prev_current` — line 641.

### 2.7 Table: `audit_logs` (lines 666-733)

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | `default=uuid.uuid4` |
| `actor_id` | UUID (FK -> `users.id` ON DELETE SET NULL) | Nullable, INDEX |
| `action` | String(100) | NOT NULL, INDEX |
| `details` | JSON | NOT NULL, default=`{}` |
| `ip_address` | String(45) | Nullable |
| `user_agent` | String(255) | Nullable |
| `created_at` | DateTime(tz) | NOT NULL, INDEX |

Indexes: `idx_audit_logs_actor_action`, `idx_audit_logs_created_at` — lines 713-714.

Audit actions present in code: `LOGIN_FAILED`, `LOGIN_SUCCESS`, `GOOGLE_LOGIN_SUCCESS`, `MFA_FAILED`, `MFA_SUCCESS`, `USER_LOGOUT`, `USER_REGISTER_PUBLISHER`, `USER_REGISTER_ADMIN`, `USER_DEACTIVATED`, `USER_REACTIVATED`, `ROLE_ASSIGNED`, `CONTENT_REGISTER`, `CONTENT_SUPERSEDED`, `CONTENT_REVOKED`, `CREDENTIAL_CREATED`, `CREDENTIAL_REVOKED`, `CREDENTIAL_SUSPENDED`.

### 2.8 Table: `verification_attempts` (lines 740-820)

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | `default=uuid.uuid4` |
| `submitted_hash` | String(64) | NOT NULL, INDEX |
| `matched_content_id` | UUID (FK -> `registered_contents.id` ON DELETE SET NULL) | Nullable, INDEX |
| `verdict` | Enum(VerificationVerdict) | NOT NULL, INDEX |
| `evidence_bundle` | JSON | NOT NULL, default=`{}` |
| `confidence_score` | Float | NOT NULL, default=0.0 |
| `verification_time_ms` | Integer | NOT NULL, default=0 |
| `created_at` | DateTime(tz) | NOT NULL, INDEX |

### 2.9 Table: `domain_whitelists` (lines 827-873)

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID (PK) | `default=uuid.uuid4` |
| `domain` | String(255) | UNIQUE, NOT NULL, INDEX |
| `allowed_roles` | JSON | NOT NULL, default=`[]` |
| `is_active` | Boolean | NOT NULL, default=True, INDEX |
| `created_at` | DateTime(tz) | NOT NULL |

Used during Google OAuth provisioning to auto-assign roles to domains — `backend/app/services/auth_service.py:294-303`.

---

## SECTION 3 — CRYPTOGRAPHIC MECHANICS

### 3.1 Ed25519 Keypair Management

File: `backend/app/core/signature_service.py` — `KeyManager` class, lines 29-153.

- **Key generation**: `ed25519.Ed25519PrivateKey.generate()` via Python `cryptography` library — line 35.
- **Private key serialization**: PKCS8 PEM format, with optional `BestAvailableEncryption` password — lines 40-55.
- **Public key serialization**: SubjectPublicKeyInfo PEM format — lines 57-64.
- **Deserialization**: Handles PEM (`BEGIN PUBLIC KEY`), raw Base64 (44-byte), and hex-encoded public keys — lines 79-96.
- **Database storage**: Public key (PEM string) stored in `users.public_key` column — `KeyManager.store_keypair`, lines 118-134.

### 3.2 Manifest Structure (C2PA-inspired)

File: `backend/app/core/signature_service.py` — `ManifestService`, lines 228-306.

`create_manifest()` at lines 231-248 produces:

```json
{
  "manifest_version": "1.0",
  "publisher_id": "<UUID>",
  "content_hash": "<sha256 lowercase>",
  "content_type": "<UPPERCASE enum>",
  "timestamp": "<ISO 8601 UTC>",
  "signing_algorithm": "Ed25519",
  "metadata": {}
}
```

`publisher_public_key`, `publisher_name`, `publisher_domain` are **added by the caller** (`publisher_service.py:240-242`) before signing, making the manifest self-contained.

**Canonical serialization** (`serialize_manifest`, lines 250-258): `json.dumps(manifest, sort_keys=True, separators=(',',':'), ensure_ascii=True)` into UTF-8 bytes. This is what gets signed and what verification re-derives — deterministic.

**Signing** (`SignatureService.sign_manifest`, lines 195-203): canonicalizes the manifest -> calls `private_key.sign(payload)` -> `base64.b64encode(signature_bytes)`.

**Manifest validation** (`validate_manifest`, lines 270-298): checks required keys (`manifest_version`, `publisher_id`, `content_hash`, `content_type`, `timestamp`, `signing_algorithm`), validates `content_hash` is a 64-char hex string, and asserts `signing_algorithm == "Ed25519"`.

### 3.3 SHA-256 Cryptographic Hash

File: `backend/app/core/hash_service.py` — `SHA256Service`, lines 36-106.

- **File hashing** (`calculate_file_hash`): streaming 64-KB chunks — lines 39-71.
- **Bytes hashing** (`calculate_bytes_hash`): single `hashlib.sha256(data).hexdigest()` call — lines 73-86.
- **Verification** (`verify_file_hash`): compares hashes via a second SHA-256 round to prevent length-extension timing attacks — lines 89-106.

### 3.4 Perceptual Hashing

File: `backend/app/core/hash_service.py` — `PerceptualHashService`, lines 159-404.

| Content Type | Algorithm | Implementation |
|---|---|---|
| **Image** | pHash (DCT) + dHash (gradient) | `imagehash.phash()` / `imagehash.dhash()` via `PIL.Image` — lines 162-200 |
| **Video** | Frame-level pHash + dHash -> composite SHA-256 | OpenCV frame extraction, `ThreadPoolExecutor` parallel hashing, composite = SHA-256 of all frame phashes — lines 202-272 |
| **Audio** | MFCC + Chroma fingerprint | `librosa.feature.mfcc()` (13 coefficients) + `librosa.feature.chroma_stft()` (12 chromas), mean-pooled, SHA-256 of float32 bytes — lines 274-319 |

**Defensive limits** enforced in code:

| Limit | Value | Location |
|---|---|---|
| PIL decompression bomb cap | 50 MP | `hash_service.py:120` |
| Image pixel dimension cap (hashing) | 4096x4096 | lines 136-138 |
| Video frame cap | 120 frames | lines 233-253 |
| Video duration cap | 600s (10 min) | lines 233-253 |
| Video frame resolution cap | 2048x2048 | lines 147-148 |
| Audio duration cap | 300s | line 301 |

**Similarity comparison** (`compare_perceptual_hashes`, lines 321-397):
- Image: Hamming distance via `imagehash.hex_to_hash(h1) - h2` -> `100 * (1 - hamming/max_bits)`.
- Video: direct lockstep frame comparison (returns immediately if >= 95% and equal count), then sequence alignment matching shorter->longer with top-80% mean — lines 356-371.

### 3.5 Hash Chain (Tamper-Evident Ledger)

File: `backend/app/core/hash_service.py` — `HashChainService`, lines 412-573.

- **Genesis hash**: 64-character zero string (`"0" * 64`) — line 29.
- **Block hash formula** (`calculate_block_hash`, lines 428-451):
  ```
  SHA-256( "{prev_hash}|{content_id}|{iso_timestamp}|{json_payload}" )
  ```
  where `json_payload` = `json.dumps(data, sort_keys=True)`.
- **Add block** (`add_block`, lines 453-498): fetches latest entry by `ORDER BY id DESC LIMIT 1`, sets `prev_hash = latest.current_hash` (or genesis if empty), calculates `current_hash`, commits `HashChainEntry` row.
- **Chain verification** (`verify_chain`, lines 500-532): fetches all entries `ORDER BY id ASC`, walks from genesis re-checking `entry.prev_hash == expected_prev_hash`. Returns `(True, None)` or `(False, broken_entry.id)`.

---

## SECTION 4 — PUBLISHING WORKFLOW

File: `backend/app/services/publisher_service.py`

### 4.1 `register_content()` — 7-Step Pipeline (lines 67-296)

| Step | Action | Location |
|---|---|---|
| 1 | Save uploaded file to `uploads/processed/{uuid}_{timestamp}.{ext}` | lines 91-106 |
| 2 | Validate file: size, extension, magic bytes | lines 109-114 |
| 3 | Compute SHA-256; reject duplicate active hashes | line 121 |
| 4 | Compute perceptual hash (image/video/audio/PDF/text) | lines 138-178 |
| 5 | Find/create ACTIVE credential for publisher | lines 181-199 |
| 6 | Create C2PA-inspired manifest, Ed25519-sign it, store `CryptographicManifest` | lines 219-253 |
| 7 | Anchor to hash chain (`add_block()`), create `AuditLog`, `db.commit()` | lines 256-288 |

On any exception: deletes saved file from disk and re-raises — lines 290-296.

### 4.2 Content Lifecycle Operations

| Operation | Function | Location |
|---|---|---|
| Supersede | `supersede_content()` | `publisher_service.py:337-375` |
| Revoke content | `revoke_content()` | `publisher_service.py:377-406` |
| List | `list_content()` | lines 298-320 |
| Get by ID | `get_content()` | lines 322-334 |

Both supersede and revoke call `clear_verification_cache()` from `whatsapp_service.py` to invalidate Redis-cached verification results — lines 372-373, 402-403.

---

## SECTION 5 — CITIZEN VERIFICATION ENGINE

File: `backend/app/services/verification_service.py`

### 5.1 `VerificationService.verify_file()` (lines 79-439)

**Input handling** (lines 103-124): accepts `UploadFile`, raw `bytes`, or file path. Writes to a `NamedTemporaryFile` for uniform downstream processing.

**Step 1** — Upload validation: `validate_file_payload()` — line 128.

**Step 2** — SHA-256 of submitted file: `calculate_file_hash(temp_file_path)` — line 133.

**Step 3** — Perceptual fingerprint with timeout: `run_with_timeout(_compute_submitted_perceptual_hash, ...)` with 120s ceiling — lines 136-141.

**Step 4 — Exact Match** (lines 143-168):
- Queries `registered_contents` where `sha256_hash == submitted_hash`, `ORDER BY created_at DESC, id DESC`.
- Priority: ACTIVE > SUPERSEDED > REVOKED.

**Step 5 — Verdict determination for exact match** (lines 198-292):
- Validates hash chain (`verify_chain(db)`) — lines 219-221.
- Validates `manifest_data` via `validate_manifest()` — line 228.
- Verifies Ed25519 signature via `verify_signature(manifest_dict, signature, public_key)` — lines 241-247.

| Condition | Verdict | Confidence |
|---|---|---|
| Credential REVOKED or content REVOKED | `PROVEN_INVALID` | 1.0 |
| Credential SUSPENDED | `PROVEN_INVALID` | 0.90 |
| ACTIVE + sig_valid + manifest_valid + chain_integrity + cred_active | `VERIFIED` | 1.0 |
| ACTIVE + (sig_valid OR manifest_valid) + cred_active | `VERIFIED` | 0.95 |
| ACTIVE but crypto fails | `PROVEN_INVALID` | 0.85 |
| SUPERSEDED + cred_active | `VERIFIED` | 0.95 |
| SUPERSEDED + cred not active | `PROVEN_INVALID` | 0.95 |

**Step 6 — Perceptual fuzzy match** (lines 295-406, only when no SHA-256 exact match):
- Iterates all ACTIVE `registered_contents`.
- IMAGE vs IMAGE: `(sim_phash * 0.6) + (sim_dhash * 0.4)`.
- VIDEO vs VIDEO: frame-aligned `compare_perceptual_hashes()`.
- AUDIO vs AUDIO: `audio_fingerprint` hex Hamming distance.
- Threshold >= 70.0% -> candidate; >= 95.0% + cred_active -> `VERIFIED`; 70-95% -> `SUSPICIOUS`.

**Step 7** — Persists `VerificationAttempt` row with all evidence — lines 411-421.

**Cleanup** (lines 434-438): `finally` block deletes temp file regardless of outcome.

### 5.2 `verify_text()` (lines 441-454)

Encodes text as UTF-8 bytes, delegates to `verify_file()` with `filename="statement.txt"`.

---

## SECTION 6 — WHATSAPP INTEGRATION

File: `backend/app/services/whatsapp_service.py`

### 6.1 Webhook Flow

- **Verification (GET)** `verify_webhook()` lines 134-165: checks `hub.mode == "subscribe"` and `hub.verify_token == settings.WHATSAPP_VERIFY_TOKEN`.
- **Event processing (POST)**: `whatsapp_webhook_event()` at `webhook.py:67`. Parses JSON body, immediately returns `{"status": "EVENT_RECEIVED"}`, dispatches `process_webhook_background()` via FastAPI `BackgroundTasks` — `webhook.py:86`.
- **Background worker** (`process_webhook_background`, `webhook.py:17-28`): opens its own `SessionLocal()`, calls `handle_webhook(payload, db)`, closes session in `finally`.

### 6.2 Message Processing

`handle_webhook` (lines 266-324): iterates `entry.changes.value.messages`, caps at `MAX_BATCH_MESSAGES = 20`.

`process_message` (lines 326-497) pipeline:

1. **Deduplication** via `is_duplicate_message(msg_id)` — Redis SET NX with 24h TTL, in-memory fallback — lines 168-188.
2. **Mark as read** — `mark_message_as_read(msg_id)` (Meta Graph API call).
3. **Per-user rate limiting** — 10 requests / 60s per `from_number` via `increment_rate_counter()` — lines 356-364.
4. **Text** — SHA-256 of text -> Redis cache key `text:{hash}`, validates cache for revocation, else runs `verify_text()` — lines 381-403.
5. **Media** — downloads from Meta Graph API, validates, checks Redis cache `media:{sha256}`, runs `verify_file()` — lines 499-553.
6. **Interactive buttons** — routes `btn_proof:{verification_id}` -> `get_verification_result()`, `btn_report` -> PIB Fact Check redirect — lines 454-488.

### 6.3 Media Download (`download_media`, lines 558-631)

- Fetches media metadata URL from `https://graph.facebook.com/v18.0/{media_id}`.
- Uses `execute_with_retry()` (exponential backoff, 3 retries, 0.5s base delay) for both metadata and binary download requests — lines 576-608.
- Saves to `settings.TEMP_DIR` (`uploads/temp/`) as `NamedTemporaryFile`.

### 6.4 Cache Invalidation

- `clear_verification_cache()` (lines 204-218): clears all Redis keys matching `wa_verif_cache:*` and in-memory `_in_memory_seen_messages`. Called on credential revoke/suspend and content revoke/supersede.
- `validate_cached_verification()` (lines 220-248): before serving a cached result, re-queries `RegisteredContent` and `Credential` to detect subsequent revocation — prevents stale VERIFIED verdicts.

---

## SECTION 7 — COMPLETE API ROUTE INVENTORY

`backend/app/api/v1/__init__.py` aggregates 7 routers under `api_v1_router` (lines 5-21). Final effective prefix: `/api/v1/{router_prefix}`.

`system_router` is additionally mounted without `/api/v1` prefix at `main.py:253`, making `/health`, `/health/liveness`, `/health/readiness` accessible at root level.

### Authentication (`/api/v1/auth`)

| Method | Path | Auth Required | Rate Limit | Handler |
|---|---|---|---|---|
| POST | `/register` | None | 10/60s per IP | `register()` — `auth.py:49` |
| POST | `/login` | None | 15/60s per IP | `login()` — `auth.py:76` |
| GET | `/google` | None | None | `google_auth_url()` — `auth.py:102` |
| POST | `/google` | None | None | `google_auth()` — `auth.py:113` |
| POST | `/google/callback` | None | None | `google_callback()` — `auth.py:144` |
| POST | `/refresh` | None | None | `refresh_token_endpoint()` — `auth.py:158` |
| POST | `/logout` | Bearer (any role) | None | `logout()` — `auth.py:175` |
| POST | `/mfa/setup` | Bearer (any role) | None | `setup_mfa()` — `auth.py:192` |
| POST | `/mfa/verify` | Conditional | None | `verify_mfa()` — `auth.py:216` |

### Content Management (`/api/v1/content`)

| Method | Path | Auth Required | Handler |
|---|---|---|---|
| POST | `/register` | PUBLISHER+ | `register_content_endpoint()` — `content.py:48` |
| GET | `/{content_id}` | None (public) | `get_content_by_id()` — `content.py:104` |
| GET | `` | None (public) | `list_contents()` — `content.py:126` |
| PUT | `/{content_id}/supersede` | PUBLISHER+ | `supersede_content_endpoint()` — `content.py:154` |
| PUT | `/{content_id}/revoke` | PUBLISHER+ | `revoke_content_endpoint()` — `content.py:181` |

### Verification (`/api/v1/verify`)

| Method | Path | Auth | Rate Limit | Handler |
|---|---|---|---|---|
| POST | `` | None (public) | 30/60s per IP | `verify_media_file()` — `verify.py:28` |
| POST | `/text` | None (public) | 30/60s per IP | `verify_text_content()` — `verify.py:64` |
| GET | `/{verification_id}` | None (public) | None | `get_verification()` — `verify.py:90` |

### Credentials (`/api/v1/credentials`)

| Method | Path | Auth Required | Handler |
|---|---|---|---|
| GET | `` | Bearer (any role) | `list_credentials()` — `credentials.py:38` |
| POST | `` | PUBLISHER+ | `create_credential()` — `credentials.py:67` |
| PUT | `/{id}/revoke` | ADMIN only | `revoke_credential()` — `credentials.py:107` |
| PUT | `/{id}/suspend` | ADMIN only | `suspend_credential()` — `credentials.py:145` |

### Admin Operations (`/api/v1/admin`) — all require ADMIN role

| Method | Path | Handler |
|---|---|---|
| GET | `/users` | `list_users()` — `admin.py:41` |
| PUT | `/users/{id}/role` | `update_user_role()` — `admin.py:61` |
| GET | `/audit-logs` | `view_audit_logs()` — `admin.py:79` |
| GET | `/stats` | `system_statistics()` — `admin.py:99` |

### System Health

| Method | Path | Handler |
|---|---|---|
| GET | `/health` | `health_check()` — `system.py:27` |
| GET | `/health/liveness` | `liveness_check()` — `system.py:51` |
| GET | `/health/readiness` | `readiness_check()` — `system.py:64` |
| GET | `/api/v1/status` | `system_status()` — `system.py:89` |
| GET | `/api/v1/registry/integrity` | `registry_integrity()` — `system.py:116` |

### Webhooks (`/api/v1/webhook`)

| Method | Path | Handler |
|---|---|---|
| GET | `/whatsapp` | `whatsapp_webhook_verification()` — `webhook.py:36` |
| POST | `/whatsapp` | `whatsapp_webhook_event()` — `webhook.py:67` |

---

## SECTION 8 — SECURITY BOUNDARIES

### 8.1 Authentication Guards

`get_current_user()` (`backend/app/api/deps.py:35-92`):
1. Extracts `Bearer` token from `Authorization` header.
2. Calls `verify_token(token, expected_type="access")`: decodes JWT (HMAC-SHA256), checks `exp`, checks Redis/in-memory JTI blacklist, checks token `type` claim.
3. Checks `mfa_pending` claim — blocks MFA-incomplete sessions.
4. Looks up `User.id` from `sub` claim, checks `user.is_active`.

Role hierarchy via `require_role()` factory at `deps.py:108-124`: `ADMIN(3) > PUBLISHER(2) > VIEWER(1)`.

### 8.2 Password Security

`bcrypt` via `passlib.CryptContext` — `security.py:34`. bcrypt 4.x compatibility patch at lines 27-31.

### 8.3 JWT Tokens

| Token Type | Algorithm | Lifetime | Claims |
|---|---|---|---|
| Access | HS256 | 30 min | `sub`, `role`, `type="access"`, `jti` (UUID), `iat`, `exp` |
| Refresh | HS256 | 7 days | `sub`, `type="refresh"`, `jti`, `iat`, `exp` |

Token rotation on refresh: old refresh token blacklisted before new pair issued — `auth_service.py:388`.

### 8.4 Token Blacklist

- Redis: `SETEX blacklist:token:{jti}` with TTL = remaining token lifetime — `security.py:192`.
- In-memory fallback: `_in_memory_blacklist` dict — `security.py:38, 194-195`.

### 8.5 Rate Limiting

- IP-based via `rate_limiter()` dependency — `deps.py:133-146`.
- Redis: `INCR ratelimit:{ip}:{path}` + `EXPIRE` — `security.py:484-531`.
- In-memory sliding window fallback — `security.py:496-507`.
- WhatsApp: 10 requests / 60s per `from_number` — `whatsapp_service.py:356-364`.

### 8.6 Account Lockout

`record_failed_login()` / `is_account_locked()` — `security.py:552-629`. 5 failed attempts -> 900s (15 min) lockout. Redis keys: `failed_logins:{email}`, `account_locked:{email}` — lines 572-584.

### 8.7 TOTP Multi-Factor Authentication

`pyotp.TOTP` with `valid_window=1` (+-30s) — `security.py:420-440`. 8 backup codes (format `XXXX-XXXX`) generated at setup — `security.py:443-460`. MFA-pending sessions use a short-lived (5 min) token with `mfa_pending: True` claim — `auth_service.py:156-166`.

### 8.8 Upload Validation (Defense-in-Depth)

File: `backend/app/core/upload_validation.py`

Four layers applied to every upload:
1. **Non-empty check** — line 141.
2. **Max file size** (<= 16 MB) — line 145.
3. **Extension allowlist** — 28 permitted extensions — lines 21-32.
4. **Magic byte cross-validation** — lines 53-94:
   - Rejects: DOS/PE executables, Linux ELF, shell scripts, PHP, HTML/JS, JAR/APK.
   - Cross-mismatch: PDF signature in non-PDF, PNG in non-image, JPEG SOI in non-image, GIF in non-image.
   - Text files: rejects binary null bytes.

### 8.9 Processing Timeout

File: `backend/app/core/timeout.py`

`run_with_timeout()` (lines 28-85): wraps callable in `ThreadPoolExecutor(max_workers=1)`, calls `future.result(timeout=effective_timeout)`. On `FutureTimeoutError` raises `ProcessingTimeoutError` (HTTP 408). Default ceiling: 120s.

**Limitation documented in code** (lines 38-44): CPython threads running native C-extensions (OpenCV, NumPy) cannot be forcibly killed. The timeout unblocks the HTTP caller; the worker thread runs until the deterministic input bounds (120-frame cap, 600s video limit, 4096px resize) cause it to finish.

Applied only to the perceptual hashing step in `verify_file()` — `verification_service.py:136-141`. SHA-256, manifest validation, and chain verification run without a timeout wrapper.

### 8.10 Request Correlation IDs

File: `backend/app/core/context.py`

`ContextVar[Optional[str]]` at line 14. `set_current_request_id()` (lines 29-42) validates incoming `X-Request-ID` against `^[a-zA-Z0-9_-]{1,64}$`, generates fresh UUID if malformed. `RequestIdFilter` (lines 45-50) injects `request_id` into every log record.

### 8.11 Security Response Headers

Set by middleware at `main.py:118-124` on every response:

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy: default-src 'self'; frame-ancestors 'none';
```

---

## SECTION 9 — FRONTEND ARCHITECTURE

### 9.1 Framework

Next.js App Router (TypeScript). Root layout at `frontend/src/app/layout.tsx`. The `frontend/src/pages/` directory is empty.

### 9.2 Route Pages Present

| Route | Source File |
|---|---|
| `/` (public landing + verify) | `frontend/src/app/page.tsx` (11 KB) |
| `/login` | `frontend/src/app/login/` |
| `/register` | `frontend/src/app/register/` |
| `/dashboard` | `frontend/src/app/dashboard/page.tsx` (6.7 KB) |
| `/dashboard/content` | `frontend/src/app/dashboard/content/` |
| `/dashboard/credentials` | `frontend/src/app/dashboard/credentials/` |
| `/dashboard/register-content` | `frontend/src/app/dashboard/register-content/` |
| `/admin` | `frontend/src/app/admin/` |

### 9.3 API Client

File: `frontend/src/services/api.ts`

- Axios instance with `baseURL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"` — line 3.
- Request interceptor: attaches `Authorization: Bearer {token}` from `localStorage.access_token` — lines 13-24.
- Response interceptor: on 401, attempts token refresh via `POST /auth/refresh`, retries original request with new token. On refresh failure, clears local storage and redirects to `/login` if on protected routes — lines 27-60.

---

## SECTION 10 — DEPENDENCY INVENTORY

File: `backend/requirements.txt`

| Package | Version | Purpose |
|---|---|---|
| fastapi | 0.104.1 | Web framework |
| uvicorn[standard] | 0.24.0 | ASGI server |
| python-multipart | 0.0.6 | Multipart file upload parsing |
| sqlalchemy | 2.0.23 | ORM |
| psycopg2-binary | 2.9.9 | PostgreSQL adapter |
| alembic | 1.12.1 | Migrations (no migration files present) |
| redis | 5.0.1 | Rate limiting, blacklist, verification cache |
| cryptography | 41.0.7 | Ed25519 keypair, PEM serialization |
| python-jose[cryptography] | 3.3.0 | JWT encode/decode |
| passlib[bcrypt] | 1.7.4 | Password hashing context |
| bcrypt | 4.1.2 | bcrypt backend |
| pyotp | 2.9.0 | TOTP MFA |
| opencv-python-headless | 4.8.1.78 | Video frame extraction |
| imagehash | 4.3.1 | pHash/dHash computation |
| Pillow | 10.1.0 | Image loading/processing |
| numpy | 1.26.2 | Array operations |
| librosa | 0.10.1 | Audio feature extraction (MFCC, Chroma) |
| soundfile | 0.12.1 | Audio file I/O |
| scipy | 1.11.4 | Scientific computations (librosa dependency) |
| httpx | 0.25.2 | HTTP client for Meta Graph API / Google OAuth |
| pydantic | 2.5.2 | Data validation/schemas |
| pydantic-settings | 2.1.0 | Config from env |
| pytest | 7.4.3 | Test runner |
| PyJWT | 2.8.0 | JWT utility (present alongside python-jose; both in requirements) |

---

## SECTION 11 — FILE STORAGE MODEL

All file storage is **local filesystem** relative to the working directory:

| Purpose | Config Key | Default Value |
|---|---|---|
| Upload root | `UPLOAD_DIR` | `uploads/` |
| Temporary WhatsApp downloads | `TEMP_DIR` | `uploads/temp/` |
| Permanent registered content | `PROCESSED_DIR` | `uploads/processed/` |

Stored filename pattern: `{uuid4().hex}_{YYYYMMDDHHMMSS}.{ext}` — `publisher_service.py:97`.

Files are served statically at `/uploads/{path}` — `main.py:250`.

> **There is no cloud object storage (S3, GCS, Azure Blob, etc.).** All media files are stored on the local disk of the process running uvicorn.

---

## SECTION 12 — KNOWN GAPS / NOT IMPLEMENTED

The following are **NOT IMPLEMENTED** in the current codebase, confirmed by direct inspection:

| Feature | Evidence |
|---|---|
| Email verification sending | `resend_verification_email()` generates a JWT token but there is no email transport/SMTP client anywhere in the codebase — `auth_service.py:601-624`. |
| Alembic migration scripts | `backend/alembic/versions/` directory is empty. Schema is managed via `Base.metadata.create_all()`. |
| Watermark embedding/extraction | `watermark_data` field exists in schema (`database.py:412`) but no service generates or validates watermarks. |
| Distributed ledger / IPFS | NOT IMPLEMENTED. Hash chain is a local PostgreSQL table. |
| Publisher-A-to-Publisher-B authorization | NOT IMPLEMENTED. |
| MFA backup code redemption | Backup codes are generated (`auth.py:199`) but there is no redemption endpoint. |
| ngrok automation | `NGROK_AUTHTOKEN` config key exists (`config.py:50`) but no code starts ngrok programmatically. |
| Content-based watermark detection | `watermark_data` field in schema but no watermark reader/writer service exists. |

---

## SECTION 13 — DATA FLOW DIAGRAMS

### 13.1 Citizen Verification (WhatsApp)

```
[WhatsApp User]
     |
     | Sends image/video/audio/text to bot
     v
[Meta Cloud API] -- POST /api/v1/webhook/whatsapp --> [webhook.py]
     |
     | BackgroundTasks.add_task(process_webhook_background, payload)
     | (returns {"status":"EVENT_RECEIVED"} to Meta immediately)
     v
[whatsapp_service.handle_webhook()]
     |
     +-- text message --> verify_text() --> verify_file(bytes)
     |
     +-- media message --> download_media() [exponential backoff] -->
     |                     validate_media_file() -->
     |                     calculate_file_hash() [cache check] -->
     |                     verify_file(path)
     |
     +-- interactive button --> get_verification_result()
     v
[VerificationService.verify_file()]
     |
     +-- validate_file_payload()
     +-- calculate_file_hash() [SHA-256]
     +-- run_with_timeout(_compute_perceptual_hash, 120s)
     |
     +-- [EXACT MATCH]: query registered_contents WHERE sha256_hash=X
     |        |
     |        +-- verify_chain(db)
     |        +-- validate_manifest(manifest_data)
     |        +-- verify_signature(manifest, sig, public_key)
     |        v
     |   VERIFIED / PROVEN_INVALID / (SUPERSEDED variants)
     |
     +-- [NO EXACT MATCH]: iterate all ACTIVE registered_contents
     |        +-- compare_perceptual_hashes() [per content type]
     |        +-- >= 95% similarity --> VERIFIED
     |        +-- 70-95% similarity --> SUSPICIOUS
     |        +-- < 70% --> UNSIGNED
     v
[VerificationAttempt row persisted]
     v
[format_verification_result()] --> [send_interactive_message() --> Meta Graph API]
     v
[WhatsApp User receives VERIFIED/SUSPICIOUS/UNSIGNED/PROVEN_INVALID]
```

### 13.2 Publisher Registration (Content Publishing)

```
[Publisher / Government Official]
     |
     | POST /api/v1/content/register (multipart: file + metadata)
     v
[content.py: register_content_endpoint()]
     |
     | Depends(require_publisher) -- checks PUBLISHER role
     v
[PublisherService.register_content()]
     |
     +-- 1. Save file: uploads/processed/{uuid}_{ts}.{ext}
     +-- 2. validate_file_payload() [size, extension, magic bytes]
     +-- 3. calculate_file_hash() [SHA-256]; check duplicate
     +-- 4. generate perceptual hash [image/video/audio/pdf/text]
     +-- 5. find/create ACTIVE Credential for publisher
     +-- 6. ManifestService.create_manifest() + sign_manifest() [Ed25519]
     |        --> CryptographicManifest row persisted
     +-- 7. HashChainService.add_block() --> HashChainEntry row persisted
     +-- 7. AuditLog (CONTENT_REGISTER) persisted
     +-- 7. db.commit()
     v
[HTTP 201: ContentRegisterResponse with content_id, sha256, manifest_signature, chain_block_id]
```

---

*Audit completed. Zero speculation. Every claim sourced directly from files read during this session. No code was modified.*
