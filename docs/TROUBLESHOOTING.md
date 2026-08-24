# Production Troubleshooting & Diagnostics Guide

This document contains troubleshooting procedures for common production issues on the **Provenance & Verification Platform**.

---

## 1. Fast Health Inspection

To check the operational health of all services:
```bash
# 1. Inspect container status
docker compose -f docker-compose.prod.yml ps

# 2. Check application health endpoint
curl -i http://localhost:8000/health
```

Expected Response:
```json
{
  "status": "ok",
  "database": "connected",
  "redis": "connected",
  "timestamp": "2026-08-24T12:00:00.000000Z"
}
```

---

## 2. Common Issues & Solutions

### A. Database Connection Refused (`connection to server at "postgres" failed`)
- **Symptom**: Backend logs show `psycopg2.OperationalError: could not connect to server: Connection refused`.
- **Cause**: PostgreSQL container is still initializing or crashed due to misconfigured permissions.
- **Resolution**:
  ```bash
  # Check PostgreSQL logs
  docker logs provenance_postgres_prod

  # Verify health status
  docker inspect --format='{{json .State.Health}}' provenance_postgres_prod

  # Restart database service
  docker compose -f docker-compose.prod.yml restart postgres
  ```

### B. WhatsApp Webhook Verification Fails (403 Forbidden / Challenge Mismatch)
- **Symptom**: Meta Developer portal displays `The URL could not be validated` or returns HTTP 403.
- **Cause**: The `hub.verify_token` sent by Meta does not match `WHATSAPP_VERIFY_TOKEN` in `.env.production`.
- **Resolution**:
  ```bash
  # Check verify token configured in backend
  docker exec -it provenance_backend_prod python -c "from app.config import settings; print('Configured Token:', settings.WHATSAPP_VERIFY_TOKEN)"

  # Test endpoint manually
  curl -i "http://localhost:8000/api/v1/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=YOUR_TOKEN&hub.challenge=11223344"
  ```
  Ensure Cloudflare SSL mode is set to **Full** (not Flexible).

### C. Rate Limit / Redis Connection Issues
- **Symptom**: Health endpoint reports `"redis": "disconnected"`.
- **Cause**: Redis container is down or `REDIS_URL` is pointing to an unreachable hostname.
- **Resolution**:
  ```bash
  # Test Redis ping directly
  docker exec -it provenance_redis_prod redis-cli ping
  # Expected output: PONG

  # Inspect Redis memory usage
  docker exec -it provenance_redis_prod redis-cli info memory
  ```

### D. Audio / Video Processing Errors (`ffmpeg: not found` or `libsndfile`)
- **Symptom**: Video or audio verification fails with `FileNotFoundError` or `OSError: sndfile library not found`.
- **Cause**: Required system packages (`ffmpeg`, `libsndfile1`, `libgl1`) were not included during the Docker build.
- **Resolution**:
  ```bash
  # Verify system libraries inside container
  docker exec -it provenance_backend_prod ffmpeg -version
  docker exec -it provenance_backend_prod python -c "import soundfile, cv2, librosa; print('Media libs loaded successfully')"
  ```

### E. Restoring a Corrupted Database
- **Symptom**: Accidentally deleted records or need to restore a prior snapshot.
- **Resolution**:
  ```bash
  ./restore.sh ./backups/provenance_db_backup_YYYYMMDD_HHMMSS.sql.gz
  ```

---

## 3. Viewing Live Service Logs

```bash
# Backend logs
docker logs -f --tail=100 provenance_backend_prod

# WhatsApp inbound/outbound interaction logs
docker logs provenance_backend_prod | grep -E "WhatsApp|webhook|verdict"

# Database logs
docker logs -f --tail=50 provenance_postgres_prod

# Frontend logs
docker logs -f --tail=50 provenance_frontend_prod
```
