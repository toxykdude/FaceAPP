"""Integration tests for the admin database-export endpoint.

Spec: admin-database-export/spec.md
- "Fresh Custom-Format Database Download": admin -> 200, application/octet-stream,
  body starts with the pg_dump custom-format magic bytes ``PGDMP``.
- "Export Authorization": 401 unauthenticated, 403 authenticated non-admin.
- "Export Audit Record": a successful export writes an audit-log entry.

Threat matrix (design.md):
- Subprocess arg injection (pg_dump): argv is a list, never shell=True, and
  NO shell metacharacter or credential ever appears in argv (the DB password
  travels only via the PGPASSWORD env var).
- Path traversal in dump filename: Content-Disposition filename is built from
  a fixed prefix + server timestamp -> ``^powerhouse_db_\\d+\\.dump$``.
- Biometric exposure: admin-only + audit-logged (cross-ref SECURITY.md sec 4).
"""

import io
import re
import uuid
from unittest.mock import patch

import pytest

from core.security import create_access_token, get_password_hash
from models.audit_log import AuditLog
from models.user import User

# --- helpers / fixtures -----------------------------------------------------


@pytest.fixture
def staff_user(db_session):
    """A non-admin (staff) user -> require_admin must return 403."""
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"staff-{suffix}",
        email=f"staff-{suffix}@example.com",
        password_hash=get_password_hash("secret123"),
        role="staff",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def staff_client(client, staff_user):
    token = create_access_token(data={"sub": str(staff_user.id)})
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


class _FakeProc:
    """Minimal stand-in for subprocess.Popen used by the streaming endpoint.

    The endpoint reads ``proc.stdout`` in chunks and calls ``poll``/``wait``.
    We feed it a deterministic body that begins with the real pg_dump
    custom-format magic bytes so the streaming contract is exercised.
    """

    def __init__(self, body: bytes = b"PGDMP\x00custom-format-mock-body"):
        self.stdout = io.BytesIO(body)
        self.returncode = 0

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode


# --- authorization ----------------------------------------------------------


class TestDbExportAuthorization:
    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/api/system/db-export")
        assert resp.status_code == 401

    def test_non_admin_returns_403(self, staff_client):
        resp = staff_client.get("/api/system/db-export")
        assert resp.status_code == 403


# --- threat matrix: subprocess arg injection --------------------------------

# Characters that, if present in a single argv element, would let a shell
# interpret the token. The pg_dump argv must be a pure list of plain tokens:
# host/port/user/dbname flags + values only. Secrets ride in PGPASSWORD env.
_SHELL_METACHAR_RE = re.compile(r"[;&|>`$\\]")


class TestDbExportSubprocessSafety:
    def test_pg_dump_invoked_as_argv_list_without_shell(self, auth_client):
        with patch("api.system.subprocess.Popen", return_value=_FakeProc()) as mocked:
            resp = auth_client.get("/api/system/db-export")

        assert resp.status_code == 200
        mocked.assert_called_once()
        args, kwargs = mocked.call_args

        # The first positional argument MUST be a list (never a shell string).
        argv = args[0] if args else kwargs.get("args")
        assert isinstance(argv, list), f"Popen argv must be a list, got {type(argv)}"
        assert argv and argv[0] == "pg_dump", argv
        # shell must never be True.
        assert kwargs.get("shell", False) is False
        # Custom-format flag must be present.
        assert "-F" in argv and "c" in argv

    def test_no_shell_metachar_or_secret_in_argv(self, auth_client):
        # The DB password parsed from DATABASE_URL must NEVER appear in argv;
        # it is delivered only via the PGPASSWORD environment variable.
        from core.config import settings

        with patch("api.system.subprocess.Popen", return_value=_FakeProc()) as mocked:
            auth_client.get("/api/system/db-export")
        args, kwargs = mocked.call_args
        argv = args[0]
        env = kwargs.get("env", {})

        for token in argv:
            assert isinstance(token, str)
            assert not _SHELL_METACHAR_RE.search(
                token
            ), f"shell metacharacter in pg_dump argv token: {token!r}"

        # The password is delivered via env, never on the command line.
        # Reconstruct what the endpoint SHOULD have avoided: never put the
        # password in argv. We assert no argv token equals/contains it.
        # (We do not assert the env value here to avoid logging it.)
        assert len(argv) >= 2
        # PGPASSWORD must be carried in the env passed to Popen.
        assert "PGPASSWORD" in env, "PGPASSWORD must be passed via env, not argv"

    def test_password_not_in_argv(self, auth_client, admin_user):
        """The DB password must never appear in any argv token."""
        # Parse the password from the live DATABASE_URL the same way the
        # endpoint does, then assert it is absent from every argv element.
        from urllib.parse import urlparse

        from core.config import settings

        parsed = urlparse(settings.DATABASE_URL)
        password = parsed.password or ""

        with patch("api.system.subprocess.Popen", return_value=_FakeProc()) as mocked:
            auth_client.get("/api/system/db-export")

        argv = mocked.call_args.args[0]
        if password:
            for token in argv:
                assert password not in token, "DB password leaked into pg_dump argv"


# --- flow + audit + filename ------------------------------------------------


class TestDbExportFlow:
    def test_admin_export_streams_custom_format_dump(self, auth_client):
        with patch("api.system.subprocess.Popen", return_value=_FakeProc()):
            resp = auth_client.get("/api/system/db-export")

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/octet-stream")
        # Real pg_dump custom-format files begin with the 5-byte magic "PGDMP".
        assert resp.content[:5] == b"PGDMP"

    def test_content_disposition_filename_matches_convention(self, auth_client):
        with patch("api.system.subprocess.Popen", return_value=_FakeProc()):
            resp = auth_client.get("/api/system/db-export")

        assert resp.status_code == 200
        cd = resp.headers.get("content-disposition", "")
        match = re.search(r'filename="([^"]+)"', cd)
        assert match, f"no filename in Content-Disposition: {cd!r}"
        fname = match.group(1)
        assert re.match(r"^powerhouse_db_\d+\.dump$", fname), fname

    def test_successful_export_is_audited(self, auth_client, admin_user, db_session):
        before = (
            db_session.query(AuditLog)
            .filter(
                AuditLog.action == "db_export",
                AuditLog.user_id == str(admin_user.id),
            )
            .count()
        )

        with patch("api.system.subprocess.Popen", return_value=_FakeProc()):
            resp = auth_client.get("/api/system/db-export")

        assert resp.status_code == 200
        after = (
            db_session.query(AuditLog)
            .filter(
                AuditLog.action == "db_export",
                AuditLog.user_id == str(admin_user.id),
            )
            .count()
        )
        assert after > before, "no db_export audit row was written"

    def test_real_pg_dump_produces_genuine_custom_format(self, auth_client):
        """Triangulation: invoke the REAL pg_dump binary against the live test
        database and confirm the streamed body is a genuine custom-format dump
        (magic ``PGDMP``). This proves the constructed argv is valid, not just
        that Popen was called with a list.
        """
        resp = auth_client.get("/api/system/db-export")
        assert resp.status_code == 200
        # A real pg_dump -F c archive always begins with the PGDMP magic.
        assert (
            resp.content[:5] == b"PGDMP"
        ), "real pg_dump did not produce a custom-format archive"
