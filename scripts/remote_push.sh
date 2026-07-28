#!/usr/bin/env bash
#
# remote_push.sh — replicate local backup artifacts to a remote target.
#
# Invoked by backup.sh in WARN-ONLY mode: a failure here MUST NOT abort the
# local backup or retention. The caller treats a non-zero exit as a logged
# "unsuccessful remote replication" and continues.
#
# Security contract (SECURITY.md sec 2, admin-data-tools threat matrix):
#   * Credentials are read ONLY from environment variables (sourced from .env
#     by backup.sh). No credential value is ever echoed to stdout/stderr/logs.
#   * No ``eval`` is used anywhere; every variable is double-quoted.
#   * Transport is selected by BACKUP_REMOTE_TYPE (none|smb|nfs|rsync).
#
# Env vars consumed:
#   BACKUP_REMOTE_TYPE   none|smb|nfs|rsync  (default: none -> no-op success)
#   BACKUP_DIR           local artifacts to replicate
#   LOG_FILE             shared backup log path
#   RSYNC_USER/HOST/PATH rsync target (or BACKUP_REMOTE_TARGET=user@host:/path)
#   SMB_SHARE/SMB_USER/SMB_PASS/SMB_PATH   smbclient target
#   NFS_MOUNT            pre-mounted NFS directory to copy into
#
# Exit codes: 0 = remote replication succeeded (or intentionally skipped);
#             non-zero = remote replication failed (caller warns + continues).

# NOTE: deliberately NO `set -e` — each transport traps its own failure and
# returns explicitly so the script never exits before it can warn.
set -uo pipefail

LOG_FILE="${LOG_FILE:-/var/log/powerhouse-backup.log}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/powerhouse}"
REMOTE_TYPE="${BACKUP_REMOTE_TYPE:-none}"

_log() {
    # Append one line to the shared backup log. Never log credential values.
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# ---------------------------------------------------------------------------
# rsync
# ---------------------------------------------------------------------------
push_rsync() {
    local user="${RSYNC_USER:-}"
    local host="${RSYNC_HOST:-}"
    local path="${RSYNC_PATH:-}"
    local target="${BACKUP_REMOTE_TARGET:-}"

    # Allow a single BACKUP_REMOTE_TARGET=user@host:/path override.
    if [ -z "$target" ]; then
        if [ -z "$host" ]; then
            _log "WARNING: rsync remote selected but RSYNC_HOST is empty; skipping remote push"
            return 1
        fi
        if [ -n "$user" ]; then
            target="${user}@${host}:${path}"
        else
            target="${host}:${path}"
        fi
    fi

    # RSYNC_PASSWORD (rsync daemon mode) and SSH keys ride in the environment;
    # this script never references or echoes them.
    if rsync -az --delete-after "$BACKUP_DIR"/ "${target}/" >> "$LOG_FILE" 2>&1; then
        _log "Remote rsync replication completed"
        return 0
    fi
    local rc=$?
    # Report only the non-sensitive target (host:path) — never creds.
    _log "WARNING: remote rsync replication failed (rc=${rc}, target='${host:-unknown}:${path}'); local backup retained"
    return 1
}

# ---------------------------------------------------------------------------
# SMB (smbclient)
# ---------------------------------------------------------------------------
push_smb() {
    local share="${SMB_SHARE:-${BACKUP_REMOTE_TARGET:-}}"
    local user="${SMB_USER:-}"
    local pass="${SMB_PASS:-}"
    local sub="${SMB_PATH:-backups}"

    if [ -z "$share" ] || [ -z "$user" ]; then
        _log "WARNING: smb remote selected but SMB_SHARE/SMB_USER not set; skipping remote push"
        return 1
    fi

    # pass is interpolated into the -U argument only; it is NEVER echoed. We
    # redirect smbclient output to the log so any server banners do not reach
    # the console; smbclient does not echo the password itself.
    if smbclient "$share" -U "${user}%${pass}" -m SMB3 \
        -D "$sub" -c "lcd ${BACKUP_DIR}; prompt OFF; recurse ON; mput *" \
        >> "$LOG_FILE" 2>&1; then
        _log "Remote SMB replication completed"
        return 0
    fi
    local rc=$?
    _log "WARNING: remote SMB replication failed (rc=${rc}, share='${share}'); local backup retained"
    return 1
}

# ---------------------------------------------------------------------------
# NFS (pre-mounted directory)
# ---------------------------------------------------------------------------
push_nfs() {
    local mount="${NFS_MOUNT:-}"
    if [ -z "$mount" ]; then
        _log "WARNING: nfs remote selected but NFS_MOUNT is empty; skipping remote push"
        return 1
    fi
    if [ ! -d "$mount" ]; then
        _log "WARNING: NFS mount point '${mount}' is not accessible; skipping remote push"
        return 1
    fi
    # Plain copy into the OS-managed mount point. No credentials here — NFS
    # auth is handled by the mount itself (sec=sys/krb5 via fstab).
    if cp -a "$BACKUP_DIR"/. "$mount"/ >> "$LOG_FILE" 2>&1; then
        _log "Remote NFS replication completed"
        return 0
    fi
    local rc=$?
    _log "WARNING: remote NFS replication failed (rc=${rc}, mount='${mount}'); local backup retained"
    return 1
}

# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------
case "$REMOTE_TYPE" in
    none|"")
        _log "Remote replication disabled (BACKUP_REMOTE_TYPE=none)"
        exit 0
        ;;
    rsync)
        push_rsync
        exit $?
        ;;
    smb)
        push_smb
        exit $?
        ;;
    nfs)
        push_nfs
        exit $?
        ;;
    *)
        _log "WARNING: unknown BACKUP_REMOTE_TYPE='${REMOTE_TYPE}'; skipping remote push"
        exit 1
        ;;
esac
