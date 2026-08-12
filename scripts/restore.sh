#!/usr/bin/env bash

# Script metadata
SCRIPT_VERSION="1.0.0"
APP_NAME="PowerHouse Membership Platform"
APP_DIR="/opt/powerhouse-membership"
DATA_DIR="/var/lib/powerhouse"
LOG_FILE="/var/log/powerhouse-restore.log"

# PowerHouse Membership Platform - Restore Script
# Restores database and biometric data from backup

set -euo pipefail

# Configuration
BACKUP_DIR="/var/backups/powerhouse"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Functions
log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" | tee -a "$LOG_FILE"
    exit 1
}

warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1" | tee -a "$LOG_FILE"
}

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    error "This script must be run as root"
fi

# Parse arguments
if [ $# -eq 0 ]; then
    echo "Usage: $0 <backup_timestamp>"
    echo ""
    echo "Available backups:"
    ls -1 "$BACKUP_DIR"/manifest_*.txt 2>/dev/null | sed 's/.*manifest_\(.*\)\.txt/  \1/' || echo "  No backups found"
    exit 1
fi

TIMESTAMP=$1

# Verify backup files exist
DB_BACKUP="$BACKUP_DIR/db_backup_${TIMESTAMP}.dump"
BIO_BACKUP="$BACKUP_DIR/biometric_backup_${TIMESTAMP}.tar.gz"
CONFIG_BACKUP="$BACKUP_DIR/config_backup_${TIMESTAMP}.tar.gz"
CHECKSUMS="$BACKUP_DIR/checksums_${TIMESTAMP}.txt"

if [ ! -f "$DB_BACKUP" ]; then
    error "Database backup not found: $DB_BACKUP"
fi

log "Starting restore process for backup: $TIMESTAMP"

# Load database credentials
ENV_FILE="$APP_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^#' "$ENV_FILE" | grep DATABASE_URL | xargs)
fi

DB_URL="${DATABASE_URL:-}"
if [ -z "$DB_URL" ]; then
    error "DATABASE_URL not found in .env file"
fi

# Parse DATABASE_URL
DB_USER=$(echo "$DB_URL" | sed -n 's|.*://\([^:]*\):.*|\1|p')
DB_PASS=$(echo "$DB_URL" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')
DB_HOST=$(echo "$DB_URL" | sed -n 's|.*@\([^:]*\):.*|\1|p')
DB_PORT=$(echo "$DB_URL" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
DB_NAME=$(echo "$DB_URL" | sed -n 's|.*/\([^?]*\).*|\1|p')

# Verify checksums if available
if [ -f "$CHECKSUMS" ]; then
    log "Verifying backup integrity..."
    cd "$BACKUP_DIR"
    if sha256sum -c "$CHECKSUMS" 2>/dev/null; then
        log "Checksum verification passed"
    else
        warn "Checksum verification failed - proceeding anyway"
    fi
fi

# Confirmation prompt
echo ""
warn "This will OVERWRITE the current database and biometric data!"
echo "Database: $DB_NAME on $DB_HOST:$DB_PORT"
echo "Backup timestamp: $TIMESTAMP"
echo ""
read -p "Are you sure you want to continue? (yes/no): " -r
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    log "Restore cancelled by user"
    exit 0
fi

# Stop services
log "Stopping application services..."
systemctl stop powerhouse-cv || true
systemctl stop powerhouse-backend || true
sleep 2

# 1. Restore database
log "Restoring PostgreSQL database..."
PGPASSWORD="$DB_PASS" pg_restore \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    --clean \
    --if-exists \
    "$DB_BACKUP" || error "Database restore failed"

log "Database restored successfully"

# 2. Restore face data (member-photos and/or the legacy biometric_data dir)
#
# The archive carries whichever of these directories existed on the source
# host, so every step below is per-directory and conditional. Assuming a fixed
# layout here is what broke this path before: the old code chmod'ed
# biometric_data unconditionally, which under `set -e` aborts the entire
# restore on any host whose archive holds only member-photos.
FACE_DIRS="member-photos biometric_data"

if [ -f "$BIO_BACKUP" ]; then
    log "Restoring face data..."

    # Move the current copies aside so a bad restore is reversible.
    STAMP=$(date +%s)
    for d in $FACE_DIRS; do
        if [ -d "$DATA_DIR/$d" ]; then
            mv "$DATA_DIR/$d" "$DATA_DIR/${d}.old.${STAMP}"
            log "Existing $d moved aside to ${d}.old.${STAMP}"
        fi
    done

    tar -xzf "$BIO_BACKUP" -C "$DATA_DIR" || error "Face data restore failed"

    # biometric_data holds raw templates -> owner-only.
    # member-photos is served through the API (/api/members/{id}/photo) and
    # must stay readable by the backend service account, so it keeps 0750.
    if [ -d "$DATA_DIR/biometric_data" ]; then
        chmod 700 "$DATA_DIR/biometric_data"
    fi
    if [ -d "$DATA_DIR/member-photos" ]; then
        chmod 750 "$DATA_DIR/member-photos"
    fi

    RESTORED=""
    for d in $FACE_DIRS; do
        if [ -d "$DATA_DIR/$d" ]; then
            RESTORED="${RESTORED} ${d}"
        fi
    done
    log "Face data restored successfully:${RESTORED:- (archive contained none)}"
else
    warn "Face data backup not found, skipping"
fi

# 3. Restore configuration (optional)
if [ -f "$CONFIG_BACKUP" ]; then
    log "Configuration backup available at: $CONFIG_BACKUP"
    log "Manual restoration required for configuration files"
fi

# Start services
log "Starting application services..."
systemctl start powerhouse-backend
sleep 3
systemctl start powerhouse-cv

# Verify services
if systemctl is-active --quiet powerhouse-backend; then
    log "Backend service started successfully"
else
    error "Backend service failed to start"
fi

if systemctl is-active --quiet powerhouse-cv; then
    log "CV service started successfully"
else
    warn "CV service failed to start - check logs"
fi

log "Restore completed successfully!"
log "Please verify the application is working correctly"

exit 0
