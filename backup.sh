#!/bin/bash
# ============================================================================
# Deepfake-Resistant Provenance System - PostgreSQL Backup Script
# Creates compressed timestamped SQL dumps from provenance_postgres_prod
# ============================================================================

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/provenance_db_backup_${TIMESTAMP}.sql.gz"
CONTAINER_NAME="provenance_postgres_prod"

# Load DB credentials from .env.production if present
if [ -f .env.production ]; then
    export $(grep -E '^POSTGRES_' .env.production | xargs)
fi

POSTGRES_USER="${POSTGRES_USER:-provenance}"
POSTGRES_DB="${POSTGRES_DB:-provenance_db}"

mkdir -p "${BACKUP_DIR}"

echo "📦 Creating backup of database '${POSTGRES_DB}'..."

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "❌ Error: Container '${CONTAINER_NAME}' is not running."
    exit 1
fi

docker exec -t "${CONTAINER_NAME}" pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --clean --if-exists | gzip > "${BACKUP_FILE}"

if [ -s "${BACKUP_FILE}" ]; then
    FILE_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
    echo "✅ Backup completed successfully: ${BACKUP_FILE} (${FILE_SIZE})"
else
    echo "❌ Error: Backup file is empty."
    rm -f "${BACKUP_FILE}"
    exit 1
fi

# Optional retention: keep last 14 days of backups
find "${BACKUP_DIR}" -name "provenance_db_backup_*.sql.gz" -type f -mtime +14 -delete || true
