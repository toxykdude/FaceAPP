"""Secure remote-backup configuration service.

Spec: backup-remote-config/spec.md + remote-backup/spec.md
- Stores ONE JSON ``backup_remote`` setting (key ``backup_remote``, category
  ``backup``) in the existing settings table — no migration (design D1).
- Password is encrypted at rest via the proven AES-256-GCM helpers
  ``core.encryption.encrypt_string``/``decrypt_string`` (same path as RTSP
  URLs). Empty or omitted password input is a keep-sentinel (design D4).
- On every successful save the managed env file is atomically rewritten
  (temp + ``os.replace``, mode 0600, root:root where possible) with ONLY the
  transport-relevant keys — a full rewrite guarantees stale transport keys
  vanish on transport change (design D5/D6, spec "Transport changes").
- The connection probe runs a 1-byte file through
  ``["timeout","20","bash","remote_push.sh"]`` — argv LIST, ``shell=False``,
  secret delivered env-only — and returns a sanitized ``{ok,message}`` with no
  secrets or banners (design D7, spec "Bounded Sanitized Connection Test").

Security contract (SECURITY.md sec 2): the materialized env file is the ONLY
place the decrypted runtime secret lives, and it is root-only. No ciphertext or
plaintext password is ever returned to the client, written to the audit log, or
echoed in probe output.
"""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from core.encryption import decrypt_string, encrypt_string
from models.setting import Setting

SETTING_KEY = "backup_remote"
SETTING_CATEGORY = "backup"

# Default managed-env path. Tests monkeypatch THIS attribute to redirect writes
# away from /etc (the design's "test-overridable path").
BACKUP_REMOTE_ENV_PATH = "/etc/faceapp/backup-remote.env"

VALID_TYPES = {"none", "rsync", "sftp", "ftp", "smb", "nfs"}
PROBEABLE_TYPES = {"rsync", "sftp", "ftp", "smb", "nfs"}

# Probe contract (design D7): the ``timeout`` coreutil enforces the 20s wall
# clock and exits 124 when the deadline fires.
PROBE_TIMEOUT_SECONDS = "20"
PROBE_TIMEOUT_RC = 124
PROBE_HARD_TIMEOUT = 30  # safety net above the 20s coreutil deadline

_DEFAULT_PORTS = {"sftp": 22, "ftp": 21}

# remote_push.sh lives at <repo>/scripts/remote_push.sh; this module is at
# <repo>/backend/services/backup_config.py.
REMOTE_PUSH_SH = Path(__file__).resolve().parents[2] / "scripts" / "remote_push.sh"

# Env keys the probe must override/clear so the child never inherits an ambient
# production BACKUP_DIR or stale transport creds from the caller's environment.
_TRANSPORT_ENV_KEYS = (
    "RSYNC_HOST",
    "RSYNC_PATH",
    "RSYNC_USER",
    "BACKUP_REMOTE_TARGET",
    "SFTP_HOST",
    "SFTP_PORT",
    "SFTP_USER",
    "SFTP_PATH",
    "SSHPASS",
    "FTP_HOST",
    "FTP_PORT",
    "FTP_USER",
    "FTP_PASS",
    "SMB_SHARE",
    "SMB_USER",
    "SMB_PASS",
    "SMB_PATH",
    "NFS_MOUNT",
)


class BackupConfigError(ValueError):
    """Raised when a backup config fails per-transport validation."""


# --- small helpers ---------------------------------------------------------


def _clean(value):
    """Strip strings and normalize empty -> None; pass non-strings through."""
    if value is None:
        return None
    if isinstance(value, str):
        v = value.strip()
        return v if v else None
    return value


def _q(value) -> str:
    """Single-quote an env value, escaping embedded single quotes."""
    s = "" if value is None else str(value)
    return "'" + s.replace("'", "'\\''") + "'"


def _decrypt_or_empty(cfg: dict) -> str:
    """Decrypt the stored password to plaintext for the root-only env file.

    The materialized env file is the runtime secret surface; it is mode 0600
    root:root. A decrypt failure degrades to empty rather than raising so a
    rotated ENCRYPTION_KEY never crashes the backup workflow.
    """
    enc = cfg.get("password_enc")
    if not enc:
        return ""
    try:
        return decrypt_string(enc)
    except Exception:
        return ""


# --- read / mask ------------------------------------------------------------


def _read(db: Session) -> dict:
    row = db.query(Setting).filter(Setting.key == SETTING_KEY).first()
    return dict(row.value) if row and row.value else {}


def get_backup_config(db: Session) -> dict:
    """Return the masked public shape of the stored config.

    Never includes ``password_enc`` or any ciphertext/plaintext password —
    only ``has_password`` (spec "Protected Masked Configuration").
    """
    return _mask(_read(db))


def _mask(value: Optional[dict]) -> dict:
    value = value or {}
    return {
        "type": value.get("type") or "none",
        "host": value.get("host") or "",
        "port": value.get("port"),
        "share": value.get("share") or "",
        "path": value.get("path") or "",
        "username": value.get("username") or "",
        "has_password": bool(value.get("password_enc")),
    }


# --- validate ---------------------------------------------------------------


def validate(value: dict) -> dict:
    """Validate + normalize a stored-shape config.

    Raises ``BackupConfigError`` on any per-transport violation. Always
    carries ``password_enc`` through (None when absent) so callers can round-
    trip the stored secret.
    """
    raw_type = value.get("type") or "none"
    if raw_type not in VALID_TYPES:
        raise BackupConfigError(f"unknown transport: {raw_type}")

    cfg = {
        "type": raw_type,
        "host": _clean(value.get("host")) or "",
        "port": _clean(value.get("port")),
        "share": _clean(value.get("share")) or "",
        "path": _clean(value.get("path")) or "",
        "username": _clean(value.get("username")) or "",
        "password_enc": value.get("password_enc"),
    }

    host = cfg["host"]
    user = cfg["username"]
    path = cfg["path"]
    share = cfg["share"]
    has_pw = bool(cfg["password_enc"])

    if raw_type == "rsync":
        if not host or not path:
            raise BackupConfigError("rsync requires host and path")
    elif raw_type == "sftp":
        if not host or not user or not has_pw:
            raise BackupConfigError("sftp requires host, username, and password")
        cfg["port"] = cfg["port"] or _DEFAULT_PORTS["sftp"]
    elif raw_type == "ftp":
        if not host or not user or not has_pw:
            raise BackupConfigError("ftp requires host, username, and password")
        cfg["port"] = cfg["port"] or _DEFAULT_PORTS["ftp"]
    elif raw_type == "smb":
        if not share or not user or not has_pw:
            raise BackupConfigError("smb requires share, username, and password")
    elif raw_type == "nfs":
        if not path:
            raise BackupConfigError("nfs requires path")
    # none: no required fields.
    return cfg


# --- write (PUT) ------------------------------------------------------------


def apply_update(db: Session, payload: dict) -> dict:
    """Merge a PUT payload into the stored config, persist, and materialize.

    Password semantics (design D4): ``password`` omitted OR ``""`` preserves
    the existing encrypted password; a non-empty value is encrypted with
    AES-256-GCM and replaces it. Validation runs BEFORE any persist or
    materialize, so an invalid update leaves DB + env file byte-identical.

    Returns the masked config. Raises ``BackupConfigError`` on validation
    failure (caller maps to HTTP 400).
    """
    existing = _read(db)
    merged = dict(existing)

    for key in ("type", "host", "port", "share", "path", "username"):
        if key in payload:
            v = payload[key]
            merged[key] = v.strip() if isinstance(v, str) else v

    # Keep-sentinel: omitted OR empty-string password keeps the current secret.
    if "password" in payload and payload["password"]:
        merged["password_enc"] = encrypt_string(payload["password"])
    # else: merged already carries the existing password_enc from `existing`.

    validated = validate(merged)  # raises -> 400, no persist/materialize
    _persist(db, validated)
    materialize_env(validated)
    return _mask(validated)


def _persist(db: Session, cfg: dict) -> None:
    row = db.query(Setting).filter(Setting.key == SETTING_KEY).first()
    if row is None:
        row = Setting(
            key=SETTING_KEY,
            value=cfg,
            category=SETTING_CATEGORY,
            description="Remote backup transport configuration (managed by admin UI)",
        )
        db.add(row)
    else:
        row.value = cfg
    db.flush()


# --- secure env materialization --------------------------------------------


def _env_lines(cfg: dict) -> list:
    """Build the KEY='value' lines for the current transport ONLY.

    A full rewrite each save (design D6) is what guarantees stale transport
    keys disappear when the transport changes.
    """
    t = cfg["type"]
    lines = [f"BACKUP_REMOTE_TYPE={_q(t)}"]

    if t == "rsync":
        lines.append(f"RSYNC_HOST={_q(cfg.get('host'))}")
        lines.append(f"RSYNC_PATH={_q(cfg.get('path'))}")
        if cfg.get("username"):
            lines.append(f"RSYNC_USER={_q(cfg.get('username'))}")
    elif t == "sftp":
        lines.append(f"SFTP_HOST={_q(cfg.get('host'))}")
        lines.append(f"SFTP_PORT={_q(cfg.get('port') or _DEFAULT_PORTS['sftp'])}")
        lines.append(f"SFTP_USER={_q(cfg.get('username'))}")
        lines.append(f"SFTP_PATH={_q(cfg.get('path'))}")
        lines.append(f"SSHPASS={_q(_decrypt_or_empty(cfg))}")
    elif t == "ftp":
        lines.append(f"FTP_HOST={_q(cfg.get('host'))}")
        lines.append(f"FTP_PORT={_q(cfg.get('port') or _DEFAULT_PORTS['ftp'])}")
        lines.append(f"FTP_USER={_q(cfg.get('username'))}")
        lines.append(f"FTP_PASS={_q(_decrypt_or_empty(cfg))}")
    elif t == "smb":
        lines.append(f"SMB_SHARE={_q(cfg.get('share'))}")
        lines.append(f"SMB_USER={_q(cfg.get('username'))}")
        lines.append(f"SMB_PASS={_q(_decrypt_or_empty(cfg))}")
        lines.append(f"SMB_PATH={_q(cfg.get('path') or 'backups')}")
    elif t == "nfs":
        lines.append(f"NFS_MOUNT={_q(cfg.get('path'))}")
    # none: only BACKUP_REMOTE_TYPE is emitted, so remote_push.sh no-ops.
    return lines


def materialize_env(cfg: dict) -> None:
    """Atomically rewrite the managed env file (temp + os.replace, 0600).

    The temp file lives in the SAME directory as the target so os.replace is a
    single atomic rename on the same filesystem — no reader can observe
    partial content (spec "Existing file is malformed"). Ownership is set to
    root:root when running as root; mode 0600 is always enforced.
    """
    target = Path(BACKUP_REMOTE_ENV_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(_env_lines(cfg)) + "\n"

    fd, tmp_name = tempfile.mkstemp(
        prefix=".backup-remote.", dir=str(target.parent), text=True
    )
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_name, 0o600)
        _try_chown_root(tmp_name)
        os.replace(tmp_name, target)
    except Exception:
        # Never leave a partial temp file behind.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _try_chown_root(path: str) -> None:
    """Best-effort root:root ownership; silently skipped for non-root callers."""
    if os.geteuid() != 0:
        return
    try:
        shutil.chown(path, user="root", group="root")
    except (PermissionError, OSError, LookupError):
        # Mode 0600 is still enforced; ownership is best-effort.
        pass


# --- sanitized connection probe --------------------------------------------


def run_probe(db: Session) -> dict:
    """Probe the configured remote through the remote-push contract.

    Returns ``{"ok": bool, "message": str}`` with a sanitized message (no
    host/user/password tokens, no remote banner, <=200 chars). Raises
    ``BackupConfigError`` if there is nothing to probe (caller -> 400).

    The probe runs entirely inside a private temp sandbox: BACKUP_DIR and
    LOG_FILE are forced to temp paths so production local artifacts are never
    touched (spec "Probe failure MUST NOT alter local backups").
    """
    stored = _read(db)
    cfg = validate(stored)  # raises if stored config is malformed
    if cfg["type"] not in PROBEABLE_TYPES:
        raise BackupConfigError(f"nothing to probe for transport '{cfg['type']}'")

    with tempfile.TemporaryDirectory() as sandbox:
        # One-byte probe artifact (spec "using a one-byte file").
        (Path(sandbox) / "probe").write_bytes(b"x")
        log_file = str(Path(sandbox) / "probe.log")

        env = _build_probe_env(cfg, backup_dir=sandbox, log_file=log_file)
        argv = ["timeout", PROBE_TIMEOUT_SECONDS, "bash", str(REMOTE_PUSH_SH)]

        try:
            completed = subprocess.run(
                argv,
                env=env,
                capture_output=True,
                text=True,
                timeout=PROBE_HARD_TIMEOUT,
            )
            rc = completed.returncode
            last_line = _last_log_line(log_file, completed)
        except subprocess.TimeoutExpired:
            # The hard safety net fired before the coreutil could — still a
            # bounded, sanitized timeout outcome.
            return {"ok": False, "message": "probe timed out"}

    message = _sanitize_message(last_line, rc, cfg)
    return {"ok": rc == 0, "message": message}


def _build_probe_env(cfg: dict, backup_dir: str, log_file: str) -> dict:
    """Build the child env: decrypt the secret env-only, sandbox BACKUP_DIR."""
    env = os.environ.copy()
    # Force the probe into its private sandbox regardless of ambient config.
    env["BACKUP_DIR"] = backup_dir
    env["LOG_FILE"] = log_file
    env["DATA_DIR"] = backup_dir  # avoid touching real biometric dirs too
    env["RETENTION_DAYS"] = "3650"  # neutralize retention inside the sandbox
    # Clear every transport key so only the decrypted managed values apply.
    for key in _TRANSPORT_ENV_KEYS:
        env.pop(key, None)

    env["BACKUP_REMOTE_TYPE"] = cfg["type"]
    t = cfg["type"]
    if t == "rsync":
        env["RSYNC_HOST"] = cfg.get("host") or ""
        env["RSYNC_PATH"] = cfg.get("path") or ""
        if cfg.get("username"):
            env["RSYNC_USER"] = cfg["username"]
    elif t == "sftp":
        env["SFTP_HOST"] = cfg.get("host") or ""
        env["SFTP_PORT"] = str(cfg.get("port") or _DEFAULT_PORTS["sftp"])
        env["SFTP_USER"] = cfg.get("username") or ""
        env["SFTP_PATH"] = cfg.get("path") or ""
        env["SSHPASS"] = _decrypt_or_empty(cfg)
    elif t == "ftp":
        env["FTP_HOST"] = cfg.get("host") or ""
        env["FTP_PORT"] = str(cfg.get("port") or _DEFAULT_PORTS["ftp"])
        env["FTP_USER"] = cfg.get("username") or ""
        env["FTP_PASS"] = _decrypt_or_empty(cfg)
    elif t == "smb":
        env["SMB_SHARE"] = cfg.get("share") or ""
        env["SMB_USER"] = cfg.get("username") or ""
        env["SMB_PASS"] = _decrypt_or_empty(cfg)
        env["SMB_PATH"] = cfg.get("path") or "backups"
    elif t == "nfs":
        env["NFS_MOUNT"] = cfg.get("path") or ""
    return env


def _last_log_line(log_path: str, completed) -> str:
    """Last non-empty line from the probe log, falling back to captured I/O."""
    text = ""
    p = Path(log_path)
    if p.exists():
        text = p.read_text()
    if not text.strip():
        text = (completed.stderr or "") + "\n" + (completed.stdout or "")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def _sanitize_message(raw: str, rc: int, cfg: dict) -> str:
    """Scrub host/user/path/share/password tokens; bound to 200 chars."""
    if rc == 0:
        base = "connection succeeded"
    elif rc == PROBE_TIMEOUT_RC:
        base = "probe timed out after 20s"
    else:
        base = raw or "remote push failed"

    secrets = [
        cfg.get("host"),
        cfg.get("username"),
        cfg.get("share"),
        cfg.get("path"),
        _decrypt_or_empty(cfg),
    ]
    msg = base
    for s in secrets:
        if s:
            msg = msg.replace(str(s), "***")
    # Scrub any lingering key=value credential patterns.
    msg = re.sub(r"(?i)(password|passwd|secret|token)\s*[=:]\s*\S+", "***", msg)
    msg = re.sub(r"\s+", " ", msg).strip()
    return msg[:200]
