#!/usr/bin/env bash

# PowerHouse Membership Platform - Automated Backup Script
#
# Backs up database (pg_dump -F c), biometric data, and configuration, then
# replicates the artifacts to an environment-configured remote target (see
# remote_push.sh) and finally prunes local artifacts older than the retention
# window.
#
# Failure model (remote-backup spec):
#   * Local backup failure   -> fatal (exit non-zero).
#   * Remote push failure    -> WARN-ONLY (logged, local backup retained).
#   * Local retention        -> ALWAYS runs, even after a remote failure.
#
# Security contract (SECURITY.md sec 2, threat matrix):
#   * Database + remote credentials are sourced ONLY from env (the application
#     .env and, when present, the DB-managed /etc/faceapp/backup-remote.env).
#   * No credential value is ever written to the log or manifest.
#   * All variables are quoted; no eval is used anywhere.

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration (all paths env-overridable so the script is testable in a tmp
# tree without touching /var).
# ---------------------------------------------------------------------------
BACKUP_DIR="${BACKUP_DIR:-/var/backups/powerhouse}"
DATA_DIR="${DATA_DIR:-/var/lib/powerhouse}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${LOG_FILE:-/var/log/powerhouse-backup.log}"
ENV_FILE="${ENV_FILE:-/opt/powerhouse-membership/.env}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Source .env (env-only credentials). Skip silently when absent so the script
# still works in test harnesses that inject env directly.
# ---------------------------------------------------------------------------
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck source=/dev/null
    . "$ENV_FILE"
    set +a
fi

# ---------------------------------------------------------------------------
# Source the DB-managed remote-backup env AFTER .env so admin-managed values
# override fallback values (spec 'Managed Environment Override'). Written
# atomically (0600 root:root) by the backend backup_config service on each
# admin save. Absent on fresh installs -> pure .env fallback, unchanged.
# ---------------------------------------------------------------------------
if [ -f /etc/faceapp/backup-remote.env ]; then
    set -a
    # shellcheck source=/dev/null
    . /etc/faceapp/backup-remote.env
    set +a
fi

# Extract database connection details from DATABASE_URL.
# Format: postgresql://user:pass@host:port/dbname
DB_URL="${DATABASE_URL:-}"
if [ -z "$DB_URL" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: DATABASE_URL not configured" | tee -a "$LOG_FILE" >&2
    exit 1
fi
DB_USER=$(echo "$DB_URL" | sed -n 's|.*://\([^:]*\):.*|\1|p')
DB_PASS=$(echo "$DB_URL" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')
DB_HOST=$(echo "$DB_URL" | sed -n 's|.*@\([^:]*\):.*|\1|p')
DB_PORT=$(echo "$DB_URL" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
DB_NAME=$(echo "$DB_URL" | sed -n 's|.*/\([^?]*\).*|\1|p')

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() {
    # Tee to stdout AND the log. Never log credential values.
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1" | tee -a "$LOG_FILE" >&2
    exit 1
}

mkdir -p "$BACKUP_DIR"
touch "$LOG_FILE"
# Export the shared paths so the remote_push.sh child (and its log lines) use
# the SAME locations even when these fell back to defaults inside this script.
export BACKUP_DIR LOG_FILE DATA_DIR RETENTION_DAYS

log "Starting backup process..."

# ---------------------------------------------------------------------------
# 1. PostgreSQL database backup (FATAL on failure)
# ---------------------------------------------------------------------------
log "Backing up PostgreSQL database..."
# PGPASSWORD travels via env, never on the command line or in logs.
PGPASSWORD="$DB_PASS" pg_dump \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    -F c \
    -f "$BACKUP_DIR/db_backup_${TIMESTAMP}.dump" || error "Database backup failed"

log "Database backup completed: db_backup_${TIMESTAMP}.dump"

# ---------------------------------------------------------------------------
# 2. Biometric data backup
# ---------------------------------------------------------------------------
log "Backing up biometric data..."
if [ -d "$DATA_DIR/biometric_data" ]; then
    tar -czf "$BACKUP_DIR/biometric_backup_${TIMESTAMP}.tar.gz" \
        -C "$DATA_DIR" biometric_data || error "Biometric data backup failed"
    log "Biometric data backup completed: biometric_backup_${TIMESTAMP}.tar.gz"
else
    log "WARNING: Biometric data directory not found, skipping"
fi

# ---------------------------------------------------------------------------
# 3. Configuration files backup (best-effort; missing files are non-fatal)
# ---------------------------------------------------------------------------
log "Backing up configuration files..."
tar -czf "$BACKUP_DIR/config_backup_${TIMESTAMP}.tar.gz" \
    -C /opt/powerhouse-membership .env \
    -C /etc/nginx/sites-available powerhouse \
    -C /etc/systemd/system powerhouse-backend.service powerhouse-cv.service 2>/dev/null || true

log "Configuration backup completed: config_backup_${TIMESTAMP}.tar.gz"

# ---------------------------------------------------------------------------
# 4. Backup manifest (no credentials — only non-sensitive connection info)
# ---------------------------------------------------------------------------
cat > "$BACKUP_DIR/manifest_${TIMESTAMP}.txt" <<EOF
PowerHouse Membership Platform Backup
======================================
Backup Date: $(date)
Timestamp: $TIMESTAMP

Files:
- db_backup_${TIMESTAMP}.dump (PostgreSQL database)
- biometric_backup_${TIMESTAMP}.tar.gz (Biometric templates)
- config_backup_${TIMESTAMP}.tar.gz (Configuration files)

Database: $DB_NAME
Host: $DB_HOST:$DB_PORT
User: $DB_USER

To restore this backup, use:
  ./restore.sh $TIMESTAMP
EOF

log "Backup manifest created"

# ---------------------------------------------------------------------------
# 5. Checksums
# ---------------------------------------------------------------------------
log "Calculating checksums..."
cd "$BACKUP_DIR"
sha256sum db_backup_${TIMESTAMP}.dump > checksums_${TIMESTAMP}.txt
sha256sum biometric_backup_${TIMESTAMP}.tar.gz >> checksums_${TIMESTAMP}.txt 2>/dev/null || true
sha256sum config_backup_${TIMESTAMP}.tar.gz >> checksums_${TIMESTAMP}.txt 2>/dev/null || true

# ---------------------------------------------------------------------------
# 6. Remote replication (WARN-ONLY). Local retention ALWAYS runs afterwards.
# ---------------------------------------------------------------------------
log "Replicating artifacts to remote target (if configured)..."
if ! bash "${SCRIPT_DIR}/remote_push.sh"; then
    log "WARNING: remote replication reported a failure; local backup and retention continue"
fi

# ---------------------------------------------------------------------------
# 7. Local retention (ALWAYS — preserves the 30-day local window)
# ---------------------------------------------------------------------------
log "Cleaning up backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -name "*.dump" -mtime +"$RETENTION_DAYS" -delete
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +"$RETENTION_DAYS" -delete
find "$BACKUP_DIR" -name "*.txt" -mtime +"$RETENTION_DAYS" -delete

# ---------------------------------------------------------------------------
# 8. Summary
# ---------------------------------------------------------------------------
BACKUP_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
log "Backup completed successfully!"
log "Total backup size: $BACKUP_SIZE"
log "Backup location: $BACKUP_DIR"
log "Retention period: $RETENTION_DAYS days"

exit 0
