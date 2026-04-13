#!/usr/bin/env bash

# PowerHouse Membership Platform - Automated Backup Script
# Backs up database and biometric data

set -euo pipefail

# Configuration
BACKUP_DIR="/var/backups/powerhouse"
DATA_DIR="/var/lib/powerhouse"
RETENTION_DAYS=30
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="/var/log/powerhouse-backup.log"

# Load database credentials from .env
ENV_FILE="/opt/powerhouse-membership/.env"
if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^#' "$ENV_FILE" | grep DATABASE_URL | xargs)
fi

# Extract database connection details
DB_URL="${DATABASE_URL:-}"
if [ -z "$DB_URL" ]; then
    echo "ERROR: DATABASE_URL not found in .env file" | tee -a "$LOG_FILE"
    exit 1
fi

# Parse DATABASE_URL (format: postgresql://user:pass@host:port/dbname)
DB_USER=$(echo "$DB_URL" | sed -n 's|.*://\([^:]*\):.*|\1|p')
DB_PASS=$(echo "$DB_URL" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')
DB_HOST=$(echo "$DB_URL" | sed -n 's|.*@\([^:]*\):.*|\1|p')
DB_PORT=$(echo "$DB_URL" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
DB_NAME=$(echo "$DB_URL" | sed -n 's|.*/\([^?]*\).*|\1|p')

# Functions
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1" | tee -a "$LOG_FILE"
    exit 1
}

# Create backup directory
mkdir -p "$BACKUP_DIR"

log "Starting backup process..."

# 1. Backup PostgreSQL database
log "Backing up PostgreSQL database..."
PGPASSWORD="$DB_PASS" pg_dump \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    -F c \
    -f "$BACKUP_DIR/db_backup_${TIMESTAMP}.dump" || error "Database backup failed"

log "Database backup completed: db_backup_${TIMESTAMP}.dump"

# 2. Backup biometric data
log "Backing up biometric data..."
if [ -d "$DATA_DIR/biometric_data" ]; then
    tar -czf "$BACKUP_DIR/biometric_backup_${TIMESTAMP}.tar.gz" \
        -C "$DATA_DIR" biometric_data || error "Biometric data backup failed"
    log "Biometric data backup completed: biometric_backup_${TIMESTAMP}.tar.gz"
else
    log "WARNING: Biometric data directory not found, skipping"
fi

# 3. Backup configuration files
log "Backing up configuration files..."
tar -czf "$BACKUP_DIR/config_backup_${TIMESTAMP}.tar.gz" \
    -C /opt/powerhouse-membership .env \
    -C /etc/nginx/sites-available powerhouse \
    -C /etc/systemd/system powerhouse-backend.service powerhouse-cv.service 2>/dev/null || true

log "Configuration backup completed: config_backup_${TIMESTAMP}.tar.gz"

# 4. Create backup manifest
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

# 5. Calculate checksums
log "Calculating checksums..."
cd "$BACKUP_DIR"
sha256sum db_backup_${TIMESTAMP}.dump > checksums_${TIMESTAMP}.txt
sha256sum biometric_backup_${TIMESTAMP}.tar.gz >> checksums_${TIMESTAMP}.txt 2>/dev/null || true
sha256sum config_backup_${TIMESTAMP}.tar.gz >> checksums_${TIMESTAMP}.txt 2>/dev/null || true

# 6. Clean up old backups
log "Cleaning up backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -name "*.dump" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.txt" -mtime +$RETENTION_DAYS -delete

# 7. Display backup summary
BACKUP_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
log "Backup completed successfully!"
log "Total backup size: $BACKUP_SIZE"
log "Backup location: $BACKUP_DIR"
log "Retention period: $RETENTION_DAYS days"

# Optional: Send notification (uncomment if email is configured)
# echo "Backup completed successfully at $(date)" | mail -s "PowerHouse Backup Success" admin@example.com

exit 0
