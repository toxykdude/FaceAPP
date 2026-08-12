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

# Extract database connection details from the connection URL.
# Format: postgresql://user:pass@host:port/dbname
# A dedicated backup role (e.g. BYPASSRLS, for when the app DB enforces
# Row-Level Security and the runtime role cannot pg_dump) can be supplied via
# BACKUP_DATABASE_URL; when set it takes precedence over DATABASE_URL.
DB_URL="${BACKUP_DATABASE_URL:-${DATABASE_URL:-}}"
if [ -z "$DB_URL" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: no database URL configured (BACKUP_DATABASE_URL or DATABASE_URL)" | tee -a "$LOG_FILE" >&2
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
# 1b. Verify the dump is COMPLETE before calling it a backup (FATAL on failure)
#
# pg_dump exiting 0 is necessary but not sufficient, and — this is the
# non-obvious part — neither is a readable table of contents.
#
# Measured on production LXC 114, 2026-08-12. A role without BYPASSRLS dumping
# an RLS-enforced database aborts mid-COPY and leaves a 56,941-byte archive.
# That archive:
#   * still begins with the PGDMP magic bytes;
#   * is read successfully by `pg_restore -l` (rc=0);
#   * still LISTS every table, including TABLE DATA entries for members,
#     memberships and biometric_templates —
# because pg_dump writes the whole TOC before streaming any data. A TOC check
# alone therefore passes a dump that contains no rows at all.
#
# What actually separates the two is reading the archive THROUGH: the full
# dump converts to SQL with rc=0, the truncated one fails with rc=1. So the
# read-through below is the load-bearing check; the TOC check catches a
# different failure (a schema-only or table-filtered dump, which reads through
# cleanly but carries no TABLE DATA entries).
#
# Neither check touches a live database — pg_restore only decodes the file.
#
# A missing pg_restore degrades to a warning: absent tooling must not discard
# an otherwise-good backup.
# ---------------------------------------------------------------------------
DUMP_FILE="$BACKUP_DIR/db_backup_${TIMESTAMP}.dump"
# Tables without which a restored database is not the gym.
CRITICAL_TABLES="members memberships biometric_templates"

# Overridable so a host with postgresql-client outside PATH can still verify.
PG_RESTORE_BIN="${PG_RESTORE_BIN:-pg_restore}"

log "Verifying database dump..."
if ! command -v "$PG_RESTORE_BIN" >/dev/null 2>&1; then
    log "WARNING: pg_restore not found; dump NOT verified (install postgresql-client)"
else
    # (a) TOC must be readable and must carry DATA entries for the tables a
    #     migration depends on. Lines look like:
    #       "3402; 0 25741 TABLE DATA public members membership"
    if ! DUMP_TOC=$("$PG_RESTORE_BIN" -l "$DUMP_FILE" 2>&1); then
        error "Database dump is unreadable by pg_restore (corrupt archive)"
    fi
    MISSING_TABLES=""
    for tbl in $CRITICAL_TABLES; do
        if ! echo "$DUMP_TOC" | grep -qE "TABLE DATA [^ ]+ ${tbl}( |$)"; then
            MISSING_TABLES="${MISSING_TABLES} ${tbl}"
        fi
    done
    if [ -n "$MISSING_TABLES" ]; then
        error "Database dump is INCOMPLETE — no data for table(s):${MISSING_TABLES}. \
The dump cannot restore the platform."
    fi

    # (b) Read the archive end to end. This is what catches the truncated
    #     archive that (a) cannot see. Output is discarded; we only want the
    #     exit status and any decode error.
    if ! RESTORE_ERR=$("$PG_RESTORE_BIN" -f /dev/null "$DUMP_FILE" 2>&1); then
        error "Database dump is TRUNCATED or corrupt — pg_restore could not read it \
through: $(echo "$RESTORE_ERR" | head -1). If the database enforces row-level \
security, point BACKUP_DATABASE_URL at a role with BYPASSRLS and pg_read_all_data \
(see scripts/migrations/003_backup_role.sql)."
    fi

    log "Database dump verified: readable end to end, data present for $CRITICAL_TABLES"
fi

# ---------------------------------------------------------------------------
# 2. Face data backup
#
# Everything the kiosk needs to recognize a member at the door. The encrypted
# FaceNet templates live in the database (backed up above); this archive
# carries the on-disk companions:
#
#   member-photos/   profile images referenced by /api/members/{id}/photo
#   biometric_data/  legacy template directory, archived only where it exists
#
# ``snapshots/`` is deliberately NOT archived: it holds access-event camera
# frames (~1 GB per host) which are disposable evidence, not state a migration
# needs. It has its own retention policy (SNAPSHOT_RETENTION_DAYS).
#
# Missing face data is a WARNING, not an error — a fresh install legitimately
# has none, and the database backup above still succeeded.
# ---------------------------------------------------------------------------
log "Backing up face data..."
FACE_DIRS=""
for candidate in member-photos biometric_data; do
    if [ -d "$DATA_DIR/$candidate" ]; then
        FACE_DIRS="${FACE_DIRS} ${candidate}"
    fi
done

if [ -n "$FACE_DIRS" ]; then
    # Unquoted on purpose: FACE_DIRS is a whitespace-separated list of fixed
    # literals chosen above, never user input, and must expand to separate
    # tar operands.
    # shellcheck disable=SC2086
    tar -czf "$BACKUP_DIR/biometric_backup_${TIMESTAMP}.tar.gz" \
        -C "$DATA_DIR" $FACE_DIRS || error "Face data backup failed"
    log "Face data backup completed:${FACE_DIRS} -> biometric_backup_${TIMESTAMP}.tar.gz"
else
    log "WARNING: no face data found in $DATA_DIR (looked for member-photos, biometric_data); skipping"
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
