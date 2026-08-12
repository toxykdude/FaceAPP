"""System administration endpoints.

Currently exposes an audited, admin-only database-export endpoint that streams
a fresh PostgreSQL custom-format dump (``pg_dump -F c``).

Security notes (see SECURITY.md sec 2/4 and the admin-data-tools threat matrix):
- Authorization is enforced server-side via ``require_admin`` (401 unauth, 403
  non-admin) BEFORE any subprocess is started. UI visibility is not trusted.
- ``pg_dump`` is invoked with an argv LIST and ``shell=False``; the parsed DB
  password is delivered ONLY through the ``PGPASSWORD`` environment variable and
  NEVER appears on the command line or in any log.
- The download filename is built from a fixed prefix + server timestamp; it
  accepts no user-supplied path component (path-traversal safe).
- Every successful export is recorded in the audit log (``action='db_export'``).
"""

import logging
import os
import subprocess
import tempfile
import time
from urllib.parse import urlparse

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.deps import get_db, require_admin
from core.audit import log_action
from core.config import settings
from models.user import User
from services import backup_config as backup_config_service

router = APIRouter(prefix="/system", tags=["System"])

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 64 * 1024  # 64 KiB streaming chunks


class BackupConfigUpdate(BaseModel):
    """Partial, write-only backup-config payload.

    Every field is optional so callers can patch a single transport field.
    ``type`` is a plain string (validated by the service, not the schema) so
    an unknown transport yields a 400 business error rather than a 422 schema
    error. ``password`` omitted or empty acts as a keep-sentinel (design D4).
    """

    type: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    share: Optional[str] = None
    path: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


def _resolve_pg_dump_url() -> str:
    """Return the connection URL pg_dump should target for the export.

    When the ``BACKUP_DATABASE_URL`` environment variable is set (a dedicated
    backup role, e.g. BYPASSRLS, used when the primary database enforces
    Row-Level Security and the runtime role cannot pg_dump), it takes
    precedence over the runtime ``DATABASE_URL``. Read at request time; the
    URL is never logged.
    """
    return os.environ.get("BACKUP_DATABASE_URL") or settings.DATABASE_URL


def _parse_db_url(url: str) -> dict:
    """Parse a PostgreSQL connection URL into connection parameters.

    Returns a dict with keys: host, port, user, password, dbname. Values fall
    back to libpq/PostgreSQL defaults when the URL omits them. Raises 500 on a
    malformed URL so the endpoint fails closed.
    """
    parsed = urlparse(url)
    if not parsed.scheme.startswith("postgres"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="configured database URL is not a valid PostgreSQL connection string",
        )
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": parsed.username or "postgres",
        "password": parsed.password or "",
        "dbname": (parsed.path or "/").lstrip("/") or "postgres",
    }


def _build_pg_dump_argv(conn: dict, target: str) -> list:
    """Build the pg_dump argv as a plain list of string tokens.

    ``target`` is the server-generated staging path pg_dump writes to (``-f``).
    Dumping to a file rather than a stdout pipe is what lets the endpoint learn
    the exit status BEFORE choosing an HTTP status code — see
    ``export_database``.

    The password is intentionally NOT included here; it is delivered via the
    PGPASSWORD environment variable (see ``_pg_env``). No user-controlled value
    reaches this list, so there is no shell/arg-injection surface.
    """
    return [
        "pg_dump",
        "-h",
        conn["host"],
        "-p",
        conn["port"],
        "-U",
        conn["user"],
        "-d",
        conn["dbname"],
        "-F",
        "c",
        "-f",
        target,
    ]


def _pg_env(conn: dict) -> dict:
    """Build the child-process environment, injecting PGPASSWORD only."""
    env = os.environ.copy()
    env["PGPASSWORD"] = conn["password"]
    return env


# A pg_dump custom-format archive always starts with these 5 bytes. Checking
# them catches the "rc=0 but nothing usable was produced" case.
_PGDUMP_MAGIC = b"PGDMP"

# pg_dump's wording when a role without BYPASSRLS dumps an RLS-enforced table.
# This is THE failure mode on this platform (see CLAUDE.md trap 12), so it
# earns a remedy in the error rather than a generic 500.
_RLS_ABORT_MARKER = "row-level security policy"


def _sanitize_pg_dump_error(stderr: str, conn: dict) -> str:
    """Turn pg_dump stderr into an operator-facing message with no secrets.

    pg_dump can echo a connection string, so the password is redacted before
    anything is returned or logged. Only the first few lines are kept — the
    abort reason is always at the top.
    """
    password = conn.get("password") or ""
    cleaned = stderr.strip()
    if password:
        cleaned = cleaned.replace(password, "***")
    lines = [ln for ln in cleaned.splitlines() if ln.strip()][:3]
    return " | ".join(lines)


@router.get("/db-export")
def export_database(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Return a fresh, VERIFIED custom-format database dump to the administrator.

    Generates the dump on demand via ``pg_dump -F c`` (custom archive format,
    restorable with ``pg_restore``). The full database — including encrypted
    biometric templates — is included; access is admin-only and audit-logged
    (SECURITY.md sec 4, Ley 1581/2012).

    The dump is staged to a temporary file and its exit status checked BEFORE
    the response begins. That ordering is the whole point: piping pg_dump's
    stdout straight into the response makes a mid-run abort indistinguishable
    from success (headers are already sent), which is how an RLS-truncated
    ~57 KB archive was served as a 200 on production. A failed dump now yields
    a 500 with the reason, no body, and no audit record.
    """
    conn = _parse_db_url(_resolve_pg_dump_url())

    fd, staging_path = tempfile.mkstemp(prefix="powerhouse_db_", suffix=".dump")
    os.close(fd)

    try:
        argv = _build_pg_dump_argv(conn, staging_path)
        env = _pg_env(conn)

        proc = subprocess.Popen(
            argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env
        )
        _, stderr = proc.communicate()

        if proc.returncode != 0:
            detail = _sanitize_pg_dump_error(
                stderr.decode("utf-8", "replace") if stderr else "", conn
            )
            if _RLS_ABORT_MARKER in detail:
                detail = (
                    f"{detail}. The database enforces row-level security and the "
                    "connecting role cannot read every row, so pg_dump aborted "
                    "and produced an INCOMPLETE archive. Point "
                    "BACKUP_DATABASE_URL at a dedicated backup role with "
                    "BYPASSRLS and pg_read_all_data."
                )
            logger.error("database export failed (rc=%s): %s", proc.returncode, detail)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"database export failed: {detail}",
            )

        size = os.path.getsize(staging_path)
        with open(staging_path, "rb") as fh:
            magic = fh.read(len(_PGDUMP_MAGIC))
        if size == 0 or magic != _PGDUMP_MAGIC:
            logger.error(
                "database export produced an unusable archive (%d bytes)", size
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "database export failed: pg_dump reported success but did "
                    "not produce a valid custom-format archive"
                ),
            )

        # Spec: "Successful export is audited". The dump is complete and
        # verified at this point, so the record cannot describe a failed run.
        log_action(
            db,
            action="db_export",
            resource_type="system",
            user_id=str(admin.id),
            username=admin.username,
            details={"format": "pg_dump -F c", "bytes": size},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
    except Exception:
        os.unlink(staging_path)
        raise

    def _stream():
        # The staging copy holds encrypted biometric templates, so it is
        # removed as soon as the body has been handed to the client — success
        # or client disconnect alike.
        try:
            with open(staging_path, "rb") as fh:
                while True:
                    chunk = fh.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    yield chunk
        finally:
            if os.path.exists(staging_path):
                os.unlink(staging_path)

    timestamp = int(time.time())
    filename = f"powerhouse_db_{timestamp}.dump"

    return StreamingResponse(
        _stream(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(size),
        },
    )


# ---------------------------------------------------------------------------
# Remote backup configuration (spec: backup-remote-config)
#
# Admin-only GET/PUT/POST on /system/backup-config. The router stays thin:
# all crypto, per-transport validation, atomic env materialization, and the
# sanitized probe live in services/backup_config.py (design D2). Passwords are
# never returned (masked reads), never audited (only {type,host}), and never
# echoed in probe output.
# ---------------------------------------------------------------------------


def _client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/backup-config")
def get_backup_config(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Return the masked remote-backup configuration.

    Exposes ``has_password`` but never the ciphertext or plaintext password
    (spec "Protected Masked Configuration"). ``backup_remote`` is deliberately
    NOT part of ``/settings/public``.
    """
    return backup_config_service.get_backup_config(db)


@router.put("/backup-config")
def update_backup_config(
    request: Request,
    payload: BackupConfigUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Validate, persist, and materialize the remote-backup configuration.

    An empty or omitted ``password`` preserves the current encrypted secret;
    a non-empty value is encrypted with AES-256-GCM. On success the managed
    env file is atomically rewritten and a safe ``{type,host}`` audit row is
    written (no secrets). Invalid input returns 400 and changes nothing.
    """
    data = payload.model_dump(exclude_none=True)
    try:
        masked = backup_config_service.apply_update(db, data)
    except backup_config_service.BackupConfigError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    log_action(
        db,
        action="backup_config_update",
        resource_type="system",
        user_id=str(admin.id),
        username=admin.username,
        details={"type": masked["type"], "host": masked["host"]},
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return masked


@router.post("/backup-config/test")
def test_backup_config(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Run a bounded, sanitized connection probe against the stored config.

    Decrypts in-memory, runs a 1-byte probe through ``timeout 20 bash
    remote_push.sh`` (argv list, env-only secret), and returns ``{ok,message}``
    with host/user/password tokens scrubbed. Probe failure MUST NOT alter local
    backups. Audited with safe ``{type,host,ok}`` details.
    """
    try:
        result = backup_config_service.run_probe(db)
    except backup_config_service.BackupConfigError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    stored = backup_config_service.get_backup_config(db)
    log_action(
        db,
        action="backup_config_test",
        resource_type="system",
        user_id=str(admin.id),
        username=admin.username,
        details={
            "type": stored["type"],
            "host": stored["host"],
            "ok": result["ok"],
        },
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return result
