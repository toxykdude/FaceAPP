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
#     and/or the DB-managed /etc/faceapp/backup-remote.env by backup.sh). No
#     credential value is ever echoed to stdout/stderr/logs.
#   * No ``eval`` is used anywhere; every variable is double-quoted.
#   * Transport is selected by BACKUP_REMOTE_TYPE (none|rsync|sftp|ftp|smb|nfs).
#
# Env vars consumed:
#   BACKUP_REMOTE_TYPE   none|rsync|sftp|ftp|smb|nfs  (default: none -> no-op)
#   BACKUP_DIR           local artifacts to replicate
#   LOG_FILE             shared backup log path
#   RSYNC_USER/HOST/PATH rsync target (or BACKUP_REMOTE_TARGET=user@host:/path)
#   SFTP_HOST/PORT/USER/PATH + SSHPASS   sftp target (SSHPASS env-only, via sshpass -e)
#   FTP_HOST/PORT/USER + FTP_PASS        ftp target (FTP_PASS -> temp 0600 netrc only)
#   SMB_SHARE/SMB_USER/SMB_PASS/SMB_PATH   smbclient target (preflight: command -v smbclient)
#   NFS_MOUNT            pre-mounted NFS directory to copy into
#
# Exit codes: 0 = remote replication succeeded (or intentionally skipped);
#             non-zero = remote replication failed (caller warns + continues).
# Transport functions log the transport's real exit code (captured
# immediately after the command runs unguarded, never from an if-construct).

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
    local rc
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
    rsync -az --delete-after "$BACKUP_DIR"/ "${target}/" >> "$LOG_FILE" 2>&1
    rc=$?
    if [ "$rc" -eq 0 ]; then
        _log "Remote rsync replication completed"
        return 0
    fi
    # Report only the non-sensitive target (host:path) — never creds.
    _log "WARNING: remote rsync replication failed (rc=${rc}, target='${host:-unknown}:${path}'); local backup retained"
    return 1
}

# ---------------------------------------------------------------------------
# SMB (smbclient)
# ---------------------------------------------------------------------------
push_smb() {
    local rc
    local -a args
    local share="${SMB_SHARE:-${BACKUP_REMOTE_TARGET:-}}"
    local user="${SMB_USER:-}"
    local pass="${SMB_PASS:-}"
    local sub="${SMB_PATH:-}"

    if [ -z "$share" ] || [ -z "$user" ]; then
        _log "WARNING: smb remote selected but SMB_SHARE/SMB_USER not set; skipping remote push"
        return 1
    fi

    # D9: pre-flight smbclient BEFORE constructing the -U user%pass argv. A
    # fresh install without samba-client would otherwise emit an opaque
    # 'command not found' and could expose the password-bearing argv into the
    # log. The warning names the exact install package so operators can fix it
    # without server access (spec 'Fresh-Install SMB Dependency').
    if ! command -v smbclient >/dev/null 2>&1; then
        _log "WARNING: smbclient not found — install 'samba-client'; remote push skipped"
        return 1
    fi

    args=(-m SMB3 -U "$user")
    if [ -n "$sub" ]; then
        args+=(-D "$sub")
    fi
    args+=("$share" -c "lcd ${BACKUP_DIR}; prompt OFF; recurse ON; mput *")

    # smbclient reads PASSWD from its environment. Keeping it out of -U avoids
    # exposing the password in the process argv. An empty SMB_PATH targets the
    # share root; -D is only valid when the configured subdirectory exists.
    PASSWD="$pass" smbclient "${args[@]}" \
        >> "$LOG_FILE" 2>&1
    rc=$?
    if [ "$rc" -eq 0 ]; then
        _log "Remote SMB replication completed"
        return 0
    fi
    _log "WARNING: remote SMB replication failed (rc=${rc}, share='${share}'); local backup retained"
    return 1
}

# ---------------------------------------------------------------------------
# SFTP (sshpass -e sftp -b)
# ---------------------------------------------------------------------------
push_sftp() {
    local rc
    local host="${SFTP_HOST:-}"
    local port="${SFTP_PORT:-22}"
    local user="${SFTP_USER:-}"
    local path="${SFTP_PATH:-}"
    local batch

    if [ -z "$host" ] || [ -z "$user" ]; then
        _log "WARNING: sftp remote selected but SFTP_HOST/SFTP_USER not set; skipping remote push"
        return 1
    fi

    # The password travels ONLY through the SSHPASS environment variable
    # (sshpass -e). It NEVER appears on the command line, in the batch file,
    # or in any log. All variables are double-quoted; no eval is used.
    batch=$(mktemp 2>/dev/null) || {
        _log "WARNING: sftp batch temp file unavailable; skipping remote push"
        return 1
    }
    # Batch carries only the remote path + transfer commands — never creds.
    cat > "$batch" <<EOF
-mkdir ${path}
lcd ${BACKUP_DIR}
cd ${path}
put -r *
bye
EOF

    # sftp stops parsing options at the first non-option argument, so every
    # flag MUST precede the user@host destination and the destination MUST be
    # last. Putting -b after it makes sftp exit with a usage error instead of
    # connecting.
    sshpass -e sftp -P "$port" -b "$batch" "${user}@${host}" >> "$LOG_FILE" 2>&1
    rc=$?
    if [ "$rc" -eq 0 ]; then
        rm -f "$batch"
        _log "Remote SFTP replication completed"
        return 0
    fi
    rm -f "$batch"
    _log "WARNING: remote SFTP replication failed (rc=${rc}, host='${host}'); local backup retained"
    return 1
}

# ---------------------------------------------------------------------------
# FTP (curl --netrc-file with a temporary 0600 credential file)
# ---------------------------------------------------------------------------
push_ftp() {
    local rc=0
    local curl_rc=0
    local host="${FTP_HOST:-}"
    local port="${FTP_PORT:-21}"
    local user="${FTP_USER:-}"
    local pass="${FTP_PASS:-}"
    local netrc

    if [ -z "$host" ] || [ -z "$user" ]; then
        _log "WARNING: ftp remote selected but FTP_HOST/FTP_USER not set; skipping remote push"
        return 1
    fi

    # Credentials live ONLY in a temporary mode-0600 netrc file consumed by
    # curl. They NEVER appear in the URL or on the argv (spec 'FTP
    # Replication'). FTP is cleartext on the wire — the risk is documented in
    # .env.example and README and is operator-opted-in.
    netrc=$(mktemp 2>/dev/null) || {
        _log "WARNING: ftp netrc temp file unavailable; skipping remote push"
        return 1
    }
    chmod 600 "$netrc"
    cat > "$netrc" <<EOF
machine ${host}
login ${user}
password ${pass}
EOF

    local f
    for f in "$BACKUP_DIR"/*; do
        [ -f "$f" ] || continue
        # --netrc-file supplies credentials; the URL carries NO userinfo.
        curl -s --connect-timeout 20 --max-time 120 \
            --netrc-file "$netrc" \
            -T "$f" \
            "ftp://${host}:${port}/$(basename "$f")" \
            >> "$LOG_FILE" 2>&1
        curl_rc=$?
        [ "$curl_rc" -ne 0 ] && rc=$curl_rc
    done
    rm -f "$netrc"

    if [ "$rc" -eq 0 ]; then
        _log "Remote FTP replication completed"
        return 0
    fi
    _log "WARNING: remote FTP replication failed (rc=${rc}, host='${host}'); local backup retained"
    return 1
}

# ---------------------------------------------------------------------------
# NFS (pre-mounted directory)
# ---------------------------------------------------------------------------
push_nfs() {
    local rc
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
    cp -a "$BACKUP_DIR"/. "$mount"/ >> "$LOG_FILE" 2>&1
    rc=$?
    if [ "$rc" -eq 0 ]; then
        _log "Remote NFS replication completed"
        return 0
    fi
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
    sftp)
        push_sftp
        exit $?
        ;;
    ftp)
        push_ftp
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
