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

import os
import subprocess
import time
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from api.deps import get_db, require_admin
from core.audit import log_action
from core.config import settings
from models.user import User

router = APIRouter(prefix="/system", tags=["System"])

_CHUNK_SIZE = 64 * 1024  # 64 KiB streaming chunks


def _parse_db_url(url: str) -> dict:
    """Parse a PostgreSQL DATABASE_URL into connection parameters.

    Returns a dict with keys: host, port, user, password, dbname. Values fall
    back to libpq/PostgreSQL defaults when the URL omits them. Raises 500 on a
    malformed URL so the endpoint fails closed.
    """
    parsed = urlparse(url)
    if not parsed.scheme.startswith("postgres"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DATABASE_URL is not a valid PostgreSQL connection string",
        )
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": parsed.username or "postgres",
        "password": parsed.password or "",
        "dbname": (parsed.path or "/").lstrip("/") or "postgres",
    }


def _build_pg_dump_argv(conn: dict) -> list:
    """Build the pg_dump argv as a plain list of string tokens.

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
    ]


def _pg_env(conn: dict) -> dict:
    """Build the child-process environment, injecting PGPASSWORD only."""
    env = os.environ.copy()
    env["PGPASSWORD"] = conn["password"]
    return env


@router.get("/db-export")
def export_database(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Stream a fresh custom-format database dump to the administrator.

    Generates the dump on demand via ``pg_dump -F c`` (custom archive format,
    restorable with ``pg_restore``). The full database — including encrypted
    biometric templates — is included; access is admin-only and audit-logged
    (SECURITY.md sec 4, Ley 1581/2012).
    """
    conn = _parse_db_url(settings.DATABASE_URL)
    argv = _build_pg_dump_argv(conn)
    env = _pg_env(conn)

    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, env=env)
    client_host = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    admin_id = str(admin.id)
    admin_username = admin.username

    def _stream():
        try:
            while True:
                chunk = proc.stdout.read(_CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk
        finally:
            proc.stdout.close()
            returncode = proc.wait()
            if returncode == 0:
                # Spec: "Successful export is audited". Audit only on success,
                # after the dump has fully streamed. Never log credentials.
                log_action(
                    db,
                    action="db_export",
                    resource_type="system",
                    user_id=admin_id,
                    username=admin_username,
                    details={"format": "pg_dump -F c"},
                    ip_address=client_host,
                    user_agent=user_agent,
                )
                db.commit()

    timestamp = int(time.time())
    filename = f"powerhouse_db_{timestamp}.dump"

    return StreamingResponse(
        _stream(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
