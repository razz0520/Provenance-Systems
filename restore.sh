#!/bin/bash
# ============================================================================
# Deepfake-Resistant Provenance System - PostgreSQL Safe Restore Script
# Restores a compressed SQL dump to provenance_postgres_prod safely
# ============================================================================

set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <path-to-backup-file.sql.gz>"
    echo "Example: $0 ./backups/provenance_db_backup_20260824_120000.sql.gz"
    exit 1
fi

BACKUP_FILE="$1"
CONTAINER_NAME="provenance_postgres_prod"

if [ ! -f "${BACKUP_FILE}" ]; then
    echo "❌ Error: Backup file '${BACKUP_FILE}' does not exist."
    exit 1
fi

if [ -f .env.production ]; then
    export $(grep -E '^POSTGRES_' .env.production | xargs)
fi

POSTGRES_USER="${POSTGRES_USER:-provenance}"
POSTGRES_DB="${POSTGRES_DB:-provenance_db}"

echo "⚠️  WARNING: You are about to restore '${BACKUP_FILE}' into '${POSTGRES_DB}'."
echo "   This will overwrite conflicting records with the backup state."
read -p "Are you sure you want to proceed? (yes/no): " CONFIRM

if [ "${CONFIRM}" != "yes" ]; then
    echo "Restore cancelled."
    exit 0
fi

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "❌ Error: Container '${CONTAINER_NAME}' is not running."
    exit 1
fi

echo "🔄 Restoring database..."
gunzip -c "${BACKUP_FILE}" | docker exec -i "${CONTAINER_NAME}" psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"

echo "✅ Database restored successfully from ${BACKUP_FILE}."
