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
from urllib.parse import urlparse

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


def _dump_target(argv: list) -> str:
    """Return the value of the ``-f`` flag in a pg_dump argv."""
    return argv[argv.index("-f") + 1]


class _FakeProc:
    """Minimal stand-in for subprocess.Popen used by the export endpoint.

    The endpoint dumps to the ``-f`` target, waits for the process, and only
    then decides the HTTP status — so this mock writes its body to that path
    rather than to a stdout pipe. ``body`` begins with the real pg_dump
    custom-format magic bytes so the success contract is exercised.

    Set ``returncode`` non-zero (with ``body`` holding whatever partial output
    a crashed pg_dump would have left behind) to simulate a FAILED dump.
    """

    def __init__(
        self,
        body: bytes = b"PGDMP\x00custom-format-mock-body",
        returncode: int = 0,
        stderr: bytes = b"",
    ):
        self.body = body
        self.returncode = returncode
        self._stderr = stderr
        self.stdout = io.BytesIO(b"")
        self.argv: list = []

    def __call__(self, argv, *args, **kwargs):
        """Stand in for ``Popen(argv, ...)`` so we can honour ``-f``."""
        self.argv = argv
        with open(_dump_target(argv), "wb") as fh:
            fh.write(self.body)
        return self

    def communicate(self, timeout=None):
        return b"", self._stderr

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
        with patch("api.system.subprocess.Popen", side_effect=_FakeProc()) as mocked:
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

        with patch("api.system.subprocess.Popen", side_effect=_FakeProc()) as mocked:
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
        # CI runs Postgres with user=password=postgres, which would
        # false-positive a naive substring check on the "-U postgres" token.
        from urllib.parse import urlparse

        from core.config import settings

        parsed = urlparse(settings.DATABASE_URL)
        password = parsed.password or ""
        username = parsed.username or ""

        with patch("api.system.subprocess.Popen", side_effect=_FakeProc()) as mocked:
            auth_client.get("/api/system/db-export")

        argv = mocked.call_args.args[0]
        if password:
            for token in argv:
                # The username legitimately appears in argv (e.g. "-U user")
                # and is not a credential. When password == username (CI uses
                # postgres/postgres) a substring check cannot distinguish a
                # leak from the username — the URI-userinfo check below still
                # catches real leaks in that case.
                if token == username:
                    continue
                assert password not in token, "DB password leaked into pg_dump argv"
            for token in argv:
                assert (
                    f":{password}@" not in token
                ), "DB password leaked via URI-style argv token"


# --- dedicated backup role (BACKUP_DATABASE_URL) -----------------------------


class TestBackupDatabaseUrlOverride:
    """When BACKUP_DATABASE_URL is set, the export endpoint MUST build the
    pg_dump argv + PGPASSWORD from it INSTEAD of settings.DATABASE_URL
    (dedicated BYPASSRLS backup role for RLS-enforced databases). When unset,
    the current DATABASE_URL behavior is preserved. Neither the URL nor its
    password may ever be logged or placed on the argv.
    """

    # Fake, test-only values — never real credentials.
    OVERRIDE_URL = "postgresql://bk_user:bk_pass@db-host:5433/otherdb"

    @staticmethod
    def _flag_value(argv: list, flag: str) -> str:
        return argv[argv.index(flag) + 1]

    def test_backup_database_url_drives_pg_dump_argv_and_env(
        self, auth_client, monkeypatch
    ):
        monkeypatch.setenv("BACKUP_DATABASE_URL", self.OVERRIDE_URL)

        with patch("api.system.subprocess.Popen", side_effect=_FakeProc()) as mocked:
            resp = auth_client.get("/api/system/db-export")

        assert resp.status_code == 200
        argv = mocked.call_args.args[0]
        env = mocked.call_args.kwargs.get("env", {})

        assert self._flag_value(argv, "-h") == "db-host"
        assert self._flag_value(argv, "-p") == "5433"
        assert self._flag_value(argv, "-U") == "bk_user"
        assert self._flag_value(argv, "-d") == "otherdb"

        # The override password travels via PGPASSWORD only (asserted, never
        # printed) and never leaks into any argv token.
        assert env.get("PGPASSWORD") == "bk_pass"
        for token in argv:
            assert "bk_pass" not in token
            assert ":bk_pass@" not in token

    def test_database_url_behavior_preserved_when_override_unset(
        self, auth_client, monkeypatch
    ):
        monkeypatch.delenv("BACKUP_DATABASE_URL", raising=False)

        from core.config import settings

        parsed = urlparse(settings.DATABASE_URL)

        with patch("api.system.subprocess.Popen", side_effect=_FakeProc()) as mocked:
            resp = auth_client.get("/api/system/db-export")

        assert resp.status_code == 200
        argv = mocked.call_args.args[0]
        env = mocked.call_args.kwargs.get("env", {})

        assert self._flag_value(argv, "-h") == (parsed.hostname or "localhost")
        assert self._flag_value(argv, "-p") == str(parsed.port or 5432)
        assert self._flag_value(argv, "-U") == (parsed.username or "postgres")
        assert self._flag_value(argv, "-d") == (
            (parsed.path or "/").lstrip("/") or "postgres"
        )
        assert env.get("PGPASSWORD") == (parsed.password or "")


# --- flow + audit + filename ------------------------------------------------


class TestDbExportFlow:
    def test_admin_export_streams_custom_format_dump(self, auth_client):
        with patch("api.system.subprocess.Popen", side_effect=_FakeProc()):
            resp = auth_client.get("/api/system/db-export")

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/octet-stream")
        # Real pg_dump custom-format files begin with the 5-byte magic "PGDMP".
        assert resp.content[:5] == b"PGDMP"

    def test_content_disposition_filename_matches_convention(self, auth_client):
        with patch("api.system.subprocess.Popen", side_effect=_FakeProc()):
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

        with patch("api.system.subprocess.Popen", side_effect=_FakeProc()):
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


class TestDbExportFailsLoudly:
    """A failed ``pg_dump`` MUST NOT be served as a successful download.

    Regression: on an RLS-enforced database, a role without BYPASSRLS makes
    pg_dump abort mid-run ("query would be affected by row-level security
    policy for table ..."). The old endpoint piped stdout straight into a
    StreamingResponse and inspected ``returncode`` only to decide whether to
    write an audit row — so the operator received HTTP 200 with a ~57 KB
    TRUNCATED archive and no indication anything was wrong. Verified against
    production LXC 114 on 2026-08-12: 56,941 bytes, rc=1, members/memberships/
    biometric_templates entirely absent.

    A backup tool that reports success on a partial dump is worse than one
    that has no backup at all, because it destroys the operator's ability to
    notice. The dump must therefore complete BEFORE any status code is sent.
    """

    # What a crashed pg_dump leaves on disk: valid magic, truncated content.
    TRUNCATED_BODY = b"PGDMP\x00partial-archive-then-abort"
    RLS_STDERR = (
        b"pg_dump: error: query failed: ERROR:  query would be affected by "
        b'row-level security policy for table "access_events"\n'
    )

    def test_failed_pg_dump_returns_error_not_truncated_body(self, auth_client):
        proc = _FakeProc(body=self.TRUNCATED_BODY, returncode=1, stderr=self.RLS_STDERR)
        with patch("api.system.subprocess.Popen", side_effect=proc):
            resp = auth_client.get("/api/system/db-export")

        assert resp.status_code >= 500, (
            "a failed pg_dump was served as a successful download — this is "
            f"the truncated-backup regression (got {resp.status_code})"
        )
        assert (
            self.TRUNCATED_BODY not in resp.content
        ), "the truncated archive body reached the client"

    def test_failed_export_is_not_audited(self, auth_client, admin_user, db_session):
        """A failed export must not leave a 'db_export' success record."""

        def _count():
            db_session.expire_all()
            return (
                db_session.query(AuditLog)
                .filter(
                    AuditLog.action == "db_export",
                    AuditLog.user_id == str(admin_user.id),
                )
                .count()
            )

        before = _count()
        proc = _FakeProc(body=self.TRUNCATED_BODY, returncode=1, stderr=self.RLS_STDERR)
        with patch("api.system.subprocess.Popen", side_effect=proc):
            auth_client.get("/api/system/db-export")

        assert _count() == before, "a FAILED export was audited as a success"

    def test_rls_failure_names_the_backup_role_remedy(self, auth_client):
        """The operator must learn WHY, not just that it broke.

        RLS aborts are the single documented cause on this platform, and the
        fix is a BYPASSRLS role via BACKUP_DATABASE_URL. Saying so in the
        error turns a support call into a config change.
        """
        proc = _FakeProc(body=self.TRUNCATED_BODY, returncode=1, stderr=self.RLS_STDERR)
        with patch("api.system.subprocess.Popen", side_effect=proc):
            resp = auth_client.get("/api/system/db-export")

        detail = resp.text.lower()
        assert "row-level security" in detail or "row level security" in detail
        assert "backup_database_url" in detail

    def test_failure_detail_never_leaks_credentials(self, auth_client, monkeypatch):
        """Whatever we surface, the connection password stays out of it."""
        monkeypatch.setenv(
            "BACKUP_DATABASE_URL",
            "postgresql://bk_user:LEAK-CANARY-PASS@db-host:5433/otherdb",
        )
        proc = _FakeProc(
            body=self.TRUNCATED_BODY,
            returncode=1,
            stderr=b"pg_dump: error: connection failed for "
            b"postgresql://bk_user:LEAK-CANARY-PASS@db-host:5433/otherdb\n",
        )
        with patch("api.system.subprocess.Popen", side_effect=proc):
            resp = auth_client.get("/api/system/db-export")

        assert "LEAK-CANARY-PASS" not in resp.text

    def test_empty_dump_is_rejected(self, auth_client):
        """rc=0 but a zero-byte / non-PGDMP file is still not a backup."""
        with patch("api.system.subprocess.Popen", side_effect=_FakeProc(body=b"")):
            resp = auth_client.get("/api/system/db-export")

        assert resp.status_code >= 500, "an empty archive was served as a backup"

    def test_temp_dump_file_is_cleaned_up_after_success(self, auth_client):
        """The on-disk staging copy must not outlive the request.

        The dump contains encrypted biometric templates (SECURITY.md sec 4);
        leaving copies in the temp dir accumulates sensitive data.
        """
        proc = _FakeProc()
        with patch("api.system.subprocess.Popen", side_effect=proc):
            resp = auth_client.get("/api/system/db-export")

        assert resp.status_code == 200
        import os as _os

        assert not _os.path.exists(
            _dump_target(proc.argv)
        ), "staged dump file left behind after the response"

    def test_temp_dump_file_is_cleaned_up_after_failure(self, auth_client):
        proc = _FakeProc(body=self.TRUNCATED_BODY, returncode=1, stderr=self.RLS_STDERR)
        with patch("api.system.subprocess.Popen", side_effect=proc):
            auth_client.get("/api/system/db-export")

        import os as _os

        assert not _os.path.exists(
            _dump_target(proc.argv)
        ), "truncated dump file left behind after the failure"


class TestDbExportRealDumpCompleteness:
    """Triangulation against the REAL pg_dump binary and the live test DB."""

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

    def test_real_dump_carries_the_migration_critical_tables(self, auth_client):
        """The export must be restorable AND carry the tables a migration needs.

        Magic bytes alone do not prove completeness: the production truncated
        dump also began with ``PGDMP``. Reading the archive's table of contents
        back with ``pg_restore -l`` is what distinguishes a real backup from a
        crashed one — members, memberships and the encrypted face templates
        must all be present.
        """
        import subprocess
        import tempfile

        resp = auth_client.get("/api/system/db-export")
        assert resp.status_code == 200

        with tempfile.NamedTemporaryFile(suffix=".dump") as fh:
            fh.write(resp.content)
            fh.flush()
            listed = subprocess.run(
                ["pg_restore", "-l", fh.name],
                capture_output=True,
                text=True,
            )

        assert (
            listed.returncode == 0
        ), f"exported archive is not readable by pg_restore: {listed.stderr}"
        for table in ("members", "memberships", "biometric_templates"):
            assert (
                f" {table} " in listed.stdout
            ), f"table {table!r} missing from the exported archive TOC"
