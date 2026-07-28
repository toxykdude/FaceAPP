"""Isolation test for the scheduled remote-backup workflow.

Spec: remote-backup/spec.md
- "Local Backup and Retention Preservation": when the remote target is
  unreachable, the local copy + checksums MUST remain intact and retention
  MUST still run; the workflow exits 0 and logs the failure as an unsuccessful
  remote replication.
- "Environment-Only Remote Credentials": credentials are read from .env only;
  no credential value is ever written to the application database or to logs.

Threat matrix (design.md):
- Shell injection in backup.sh remote path: all remote vars consumed quoted,
  never via eval; an unreachable remote must NOT execute arbitrary commands.
- Secrets in logs: backup.sh / remote_push.sh never echo SMB_PASS/PGPASSWORD.

There is no unit-test runner for shell/systemd in this project. This test
drives ``scripts/backup.sh`` as a subprocess in an isolated tmp tree with a
mocked ``pg_dump`` and ``rsync`` and an unreachable rsync target, then asserts
the spec's isolation + retention + no-secret-leak contracts. The systemd units
and install.sh changes are covered by the manual verification steps in task C.4
(no runner exists to exercise oneshot services / timers).
"""

import os
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKUP_SH = REPO_ROOT / "scripts" / "backup.sh"


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """Build a fully isolated env + mocked binaries for one backup.sh run."""
    backup_dir = tmp_path / "backups"
    data_dir = tmp_path / "data"
    log_file = tmp_path / "backup.log"
    bin_dir = tmp_path / "bin"

    backup_dir.mkdir()
    (data_dir / "biometric_data").mkdir(parents=True)
    (data_dir / "biometric_data" / "template.bin").write_bytes(b"\x00\x01\x02")
    bin_dir.mkdir()

    # Mock pg_dump: honour -f <path> by writing a fake custom-format body.
    _write_exec(
        bin_dir / "pg_dump",
        """#!/usr/bin/env bash
f=""
prev=""
for a in "$@"; do
  if [ "$prev" = "-f" ]; then f="$a"; fi
  prev="$a"
done
[ -z "$f" ] && { echo 'mock pg_dump: no -f target' >&2; exit 1; }
printf 'PGDMP mock-dump-body' > "$f"
""",
    )

    # Mock rsync: simulate an UNREACHABLE remote (exit non-zero, message on
    # stderr). The real script must treat this as a warn-only failure.
    _write_exec(
        bin_dir / "rsync",
        """#!/usr/bin/env bash
echo 'rsync: failed to connect to nonexistent.invalid (Name or service not known)' >&2
exit 23
""",
    )

    env = os.environ.copy()
    # Put mocked binaries ahead of system PATH so backup.sh / remote_push.sh
    # resolve them first.
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    env["BACKUP_DIR"] = str(backup_dir)
    env["DATA_DIR"] = str(data_dir)
    env["LOG_FILE"] = str(log_file)
    env["ENV_FILE"] = str(tmp_path / "does-not-exist.env")
    env["RETENTION_DAYS"] = "30"
    # Live DB creds (password is a canary for log leakage).
    env["DATABASE_URL"] = (
        "postgresql://backup_user:DBPASS-SECRET@localhost:5432/membership_db"
    )
    # Remote config: rsync to an unreachable host.
    env["BACKUP_REMOTE_TYPE"] = "rsync"
    env["RSYNC_USER"] = "bkp"
    env["RSYNC_HOST"] = "nonexistent.invalid"
    env["RSYNC_PATH"] = "/srv/backups"
    # An unused SMB secret is also present in the env; it must never leak.
    env["SMB_PASS"] = "SMB-SECRET-TOKEN"

    return {
        "env": env,
        "backup_dir": backup_dir,
        "data_dir": data_dir,
        "log_file": log_file,
    }


def _seed_old_artifact(backup_dir: Path) -> Path:
    """Seed a >retention-day-old dump so we can prove retention ran."""
    old = backup_dir / "db_backup_20000101_000000.dump"
    old.write_bytes(b"ancient")
    age = time.time() - (40 * 86400)  # 40 days ago > 30-day retention
    os.utime(old, (age, age))
    return old


class TestRemoteBackupIsolation:
    def test_unreachable_remote_preserves_local_backup(self, isolated_env):
        env = isolated_env["env"]
        old_artifact = _seed_old_artifact(isolated_env["backup_dir"])
        run_start = time.time()

        proc = subprocess.run(
            ["bash", str(BACKUP_SH)],
            env=env,
            capture_output=True,
            text=True,
        )

        assert proc.returncode == 0, (
            f"backup.sh exited {proc.returncode}\nSTDOUT:\n{proc.stdout}\n"
            f"STDERR:\n{proc.stderr}"
        )

        backup_dir = isolated_env["backup_dir"]

        def _fresh(glob: str):
            return [p for p in backup_dir.glob(glob) if p.stat().st_mtime >= run_start]

        # Local artifacts survived (and were freshly produced this run) despite
        # the unreachable remote.
        assert _fresh("db_backup_*.dump"), "no local .dump produced this run"
        assert _fresh("*.tar.gz"), "no local .tar.gz produced this run"
        assert _fresh("checksums_*.txt"), "no checksums file produced this run"

        # Retention ran: the seeded 40-day-old dump MUST be gone.
        assert (
            not old_artifact.exists()
        ), "retention did not remove an artifact older than RETENTION_DAYS"

        log_text = isolated_env["log_file"].read_text()

        # Remote failure was logged as an unsuccessful replication (warn, not
        # fatal). Match either Spanish or English phrasing defensively.
        assert (
            "remote" in log_text.lower()
        ), f"remote-failure warning missing from log:\n{log_text}"

        # The transport's REAL exit code reached the warning (not masked to
        # rc=0 by the if-construct bug) — the mocked rsync exits 23.
        assert "rc=23" in log_text, f"real rsync rc missing from log:\n{log_text}"

        # Credential isolation: no secret token ever reaches the log.
        assert (
            "SMB-SECRET-TOKEN" not in log_text
        ), "SMB_PASS value leaked into backup log"
        assert "DBPASS-SECRET" not in log_text, "DB password leaked into backup log"

    def test_remote_disabled_is_noop_and_exits_zero(self, isolated_env):
        """Triangulation: BACKUP_REMOTE_TYPE=none must skip remote entirely
        and still complete local backup + retention cleanly."""
        env = isolated_env["env"]
        env["BACKUP_REMOTE_TYPE"] = "none"
        run_start = time.time()
        # Force rsync target away so remote_push is provably a no-op.
        env.pop("RSYNC_HOST", None)

        proc = subprocess.run(
            ["bash", str(BACKUP_SH)], env=env, capture_output=True, text=True
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr

        backup_dir = isolated_env["backup_dir"]
        fresh = [
            p
            for p in backup_dir.glob("db_backup_*.dump")
            if p.stat().st_mtime >= run_start
        ]
        assert fresh, "no local .dump produced in none-mode"
        log_text = isolated_env["log_file"].read_text()
        # No secret leakage even in the no-op path.
        assert "DBPASS-SECRET" not in log_text


# ---------------------------------------------------------------------------
# Mocked binaries for the new transports (sftp/ftp/smb).
# Each records its argv into MOCK_MARKER_DIR so tests can prove secrets
# travelled env-only / netrc-only and never reached argv or logs.
# ---------------------------------------------------------------------------

_MOCK_PG_DUMP = """#!/usr/bin/env bash
f=""
prev=""
for a in "$@"; do
  if [ "$prev" = "-f" ]; then f="$a"; fi
  prev="$a"
done
[ -z "$f" ] && { echo 'mock pg_dump: no -f target' >&2; exit 1; }
printf 'PGDMP mock-dump-body' > "$f"
"""

_MOCK_RSYNC_FAIL = """#!/usr/bin/env bash
echo 'rsync: failed to connect (Name or service not known)' >&2
exit 23
"""

# sshpass mock: records argv (SSHPASS must be env-only, never argv), then fails.
_MOCK_SSHPASS = """#!/usr/bin/env bash
printf '%s\\n' "$@" > "${MOCK_MARKER_DIR}/sshpass.argv"
exit 5
"""

# curl mock: records argv (FTP creds must live in --netrc-file, never argv/URL).
_MOCK_CURL = """#!/usr/bin/env bash
printf '%s\\n' "$@" > "${MOCK_MARKER_DIR}/curl.argv"
exit 7
"""

_MOCK_SMBCLIENT_FAIL = """#!/usr/bin/env bash
exit 1
"""

# smbclient mock that emits the well-known auth-failure protocol line on
# stderr and exits with a non-zero transport code.
_MOCK_SMBCLIENT_RC7 = """#!/usr/bin/env bash
echo 'session setup failed: NT_STATUS_LOGON_FAILURE' >&2
exit 7
"""

_MOCK_NOOP = """#!/usr/bin/env bash
exit 0
"""

# pg_dump mock that ALSO records argv (one token per line) and the PGPASSWORD
# it received into canary files, so tests can assert which connection the
# script targeted without ever printing the values.
_MOCK_PG_DUMP_RECORD = """#!/usr/bin/env bash
printf '%s\\n' "$@" > "${MOCK_MARKER_DIR}/pg_dump.argv"
printf '%s' "${PGPASSWORD:-}" > "${MOCK_MARKER_DIR}/pg_dump.pgpassword"
f=""
prev=""
for a in "$@"; do
  if [ "$prev" = "-f" ]; then f="$a"; fi
  prev="$a"
done
[ -z "$f" ] && { echo 'mock pg_dump: no -f target' >&2; exit 1; }
printf 'PGDMP mock-dump-body' > "$f"
"""


@pytest.fixture
def make_env(tmp_path):
    """Factory: build an isolated env + mocked binaries for one transport.

    ``with_smbclient=False`` simulates a fresh install where smbclient is NOT
    installed (the D9 pre-flight path). The factory is transport-agnostic;
    callers set the transport-specific env vars they need.
    """

    counter = {"n": 0}

    def _build(*, transport, with_smbclient=False):
        counter["n"] += 1
        tag = f"{transport}-{counter['n']}"
        backup_dir = tmp_path / f"bk-{tag}"
        data_dir = tmp_path / "data"
        log_file = tmp_path / f"backup-{tag}.log"
        bin_dir = tmp_path / "bin"
        marker_dir = tmp_path / f"markers-{tag}"

        backup_dir.mkdir()
        if not (data_dir / "biometric_data").exists():
            (data_dir / "biometric_data").mkdir(parents=True)
            (data_dir / "biometric_data" / "template.bin").write_bytes(b"\x00\x01\x02")
        bin_dir.mkdir()
        marker_dir.mkdir()

        _write_exec(bin_dir / "pg_dump", _MOCK_PG_DUMP)
        _write_exec(bin_dir / "rsync", _MOCK_RSYNC_FAIL)
        _write_exec(bin_dir / "sshpass", _MOCK_SSHPASS)
        _write_exec(
            bin_dir / "sftp", _MOCK_NOOP
        )  # sshpass execs sftp; mock fails at sshpass
        _write_exec(bin_dir / "curl", _MOCK_CURL)
        if with_smbclient:
            _write_exec(bin_dir / "smbclient", _MOCK_SMBCLIENT_FAIL)
        # else: smbclient deliberately absent -> D9 pre-flight must catch it.

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["BACKUP_DIR"] = str(backup_dir)
        env["DATA_DIR"] = str(data_dir)
        env["LOG_FILE"] = str(log_file)
        env["ENV_FILE"] = str(tmp_path / "no-such-env")
        env["RETENTION_DAYS"] = "30"
        env["MOCK_MARKER_DIR"] = str(marker_dir)
        env["DATABASE_URL"] = (
            "postgresql://backup_user:DBPASS-SECRET@localhost:5432/membership_db"
        )
        env["BACKUP_REMOTE_TYPE"] = transport

        return {
            "env": env,
            "backup_dir": backup_dir,
            "log_file": log_file,
            "marker_dir": marker_dir,
        }

    return _build


def _seed_recent(backup_dir: Path, name: str, body: bytes) -> Path:
    """Seed a recent (retention-safe) artifact that must survive a failed push."""
    f = backup_dir / name
    f.write_bytes(body)
    return f


class TestSmbMissingSmbclient:
    """Spec: remote-backup/spec.md — 'Fresh-Install SMB Dependency'.

    When smbclient is unavailable, SMB replication MUST fail warn-only with a
    warning that names ``samba-client`` (design D9), and local backup success
    MUST be preserved. The password-bearing ``-U user%pass`` argv MUST NEVER be
    built, so no credential can reach bash's 'command not found' output.
    """

    def test_smb_missing_smbclient_warns_samba_client(self, make_env):
        cfg = make_env(transport="smb", with_smbclient=False)
        env = cfg["env"]
        env["SMB_SHARE"] = "//host/share"
        env["SMB_USER"] = "smbuser"
        env["SMB_PASS"] = "SMB-SECRET-TOKEN"
        env["SMB_PATH"] = "backups"

        old_artifact = _seed_old_artifact(cfg["backup_dir"])
        run_start = time.time()

        proc = subprocess.run(
            ["bash", str(BACKUP_SH)], env=env, capture_output=True, text=True
        )
        # Warn-only: the overall backup still succeeds.
        assert proc.returncode == 0, proc.stdout + proc.stderr

        log_text = cfg["log_file"].read_text()

        # The warning identifies the exact install package.
        assert (
            "samba-client" in log_text
        ), f"missing-tool warning must name 'samba-client':\n{log_text}"

        # Fresh local artifacts were produced despite the missing tool.
        fresh = [
            p
            for p in cfg["backup_dir"].glob("db_backup_*.dump")
            if p.stat().st_mtime >= run_start
        ]
        assert fresh, "no local .dump produced during failed smb push"
        fresh_tars = [
            p
            for p in cfg["backup_dir"].glob("*.tar.gz")
            if p.stat().st_mtime >= run_start
        ]
        assert fresh_tars, "no local .tar.gz produced during failed smb push"
        fresh_checksums = [
            p
            for p in cfg["backup_dir"].glob("checksums_*.txt")
            if p.stat().st_mtime >= run_start
        ]
        assert fresh_checksums, "no checksums file produced during failed smb push"

        # Retention still ran.
        assert not old_artifact.exists(), "retention did not run after smb failure"

        # Credential isolation: the secret never reached any log/stdout/stderr.
        assert "SMB-SECRET-TOKEN" not in log_text, "SMB_PASS leaked into backup log"
        assert "SMB-SECRET-TOKEN" not in proc.stdout, "SMB_PASS leaked to stdout"
        assert "SMB-SECRET-TOKEN" not in proc.stderr, "SMB_PASS leaked to stderr"


class TestRemotePasswordsNeverLogged:
    """Spec: remote-backup/spec.md — 'Remote Secret Log Isolation'.

    SFTP/FTP password values MUST NOT appear in any log, including the success,
    warning, and failure paths. Secrets travel env-only (sshpass/SSHPASS) or
    netrc-only (curl/--netrc-file), never on the tool's argv or in a URL.
    """

    @pytest.mark.parametrize("transport", ["sftp", "ftp"])
    def test_passwords_never_in_logs_or_argv(self, make_env, transport):
        cfg = make_env(transport=transport)
        env = cfg["env"]

        if transport == "sftp":
            env["SFTP_HOST"] = "remote.invalid"
            env["SFTP_PORT"] = "22"
            env["SFTP_USER"] = "sftpuser"
            env["SFTP_PATH"] = "/bkp"
            env["SSHPASS"] = "SSHP-SECRET-TOKEN"
            marker_name = "sshpass.argv"
            secret = "SSHP-SECRET-TOKEN"
            phrase = "SFTP"
        else:
            env["FTP_HOST"] = "remote.invalid"
            env["FTP_PORT"] = "21"
            env["FTP_USER"] = "ftpuser"
            env["FTP_PASS"] = "FTPP-SECRET-TOKEN"
            marker_name = "curl.argv"
            secret = "FTPP-SECRET-TOKEN"
            phrase = "FTP"

        old_artifact = _seed_old_artifact(cfg["backup_dir"])
        run_start = time.time()

        proc = subprocess.run(
            ["bash", str(BACKUP_SH)], env=env, capture_output=True, text=True
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr

        log_text = cfg["log_file"].read_text()

        # The transport path actually ran (not the unknown-type fallback).
        assert (
            phrase in log_text
        ), f"{phrase} replication path was not exercised:\n{log_text}"

        # The tool was invoked (proves we did not trivially skip).
        argv_marker = cfg["marker_dir"] / marker_name
        assert (
            argv_marker.exists()
        ), f"{marker_name} not produced — {phrase} path did not invoke its tool"

        # Secret never reached the tool's argv (env-only / netrc-only contract).
        assert (
            secret not in argv_marker.read_text()
        ), f"{phrase} secret leaked into tool argv"

        # Secret never reached any captured output stream.
        assert secret not in log_text, f"{phrase} secret leaked into backup log"
        assert secret not in proc.stdout, f"{phrase} secret leaked to stdout"
        assert secret not in proc.stderr, f"{phrase} secret leaked to stderr"

        # Local artifacts preserved + retention ran.
        fresh = [
            p
            for p in cfg["backup_dir"].glob("db_backup_*.dump")
            if p.stat().st_mtime >= run_start
        ]
        assert fresh
        assert not old_artifact.exists()


class TestBackupDatabaseUrlOverride:
    """backup.sh MUST run pg_dump against BACKUP_DATABASE_URL when it is set
    (dedicated backup role, e.g. BYPASSRLS on an RLS-enforced database),
    falling back to DATABASE_URL otherwise. The override password travels
    env-only (PGPASSWORD) and never reaches argv or logs.
    """

    OVERRIDE_URL = "postgresql://bk_user:BK-PASS-SECRET@db-host:5433/otherdb"

    @staticmethod
    def _flag_value(tokens: list, flag: str) -> str:
        return tokens[tokens.index(flag) + 1]

    def _run_with_recording_pg_dump(self, cfg):
        bin_dir = Path(cfg["env"]["PATH"].split(":")[0])
        _write_exec(bin_dir / "pg_dump", _MOCK_PG_DUMP_RECORD)
        return subprocess.run(
            ["bash", str(BACKUP_SH)],
            env=cfg["env"],
            capture_output=True,
            text=True,
        )

    def test_pg_dump_uses_backup_database_url_when_set(self, make_env):
        cfg = make_env(transport="none")
        cfg["env"]["BACKUP_DATABASE_URL"] = self.OVERRIDE_URL

        proc = self._run_with_recording_pg_dump(cfg)
        assert proc.returncode == 0, proc.stdout + proc.stderr

        tokens = (cfg["marker_dir"] / "pg_dump.argv").read_text().splitlines()
        assert self._flag_value(tokens, "-h") == "db-host"
        assert self._flag_value(tokens, "-p") == "5433"
        assert self._flag_value(tokens, "-U") == "bk_user"
        assert self._flag_value(tokens, "-d") == "otherdb"
        # The runtime DATABASE_URL role must NOT be used when the override is set.
        assert "backup_user" not in tokens

        # PGPASSWORD came from the override, env-only (asserted, not printed).
        pgpassword = (cfg["marker_dir"] / "pg_dump.pgpassword").read_text()
        assert pgpassword == "BK-PASS-SECRET"

        # No password (override or runtime) ever reaches the logs/streams.
        log_text = cfg["log_file"].read_text()
        for secret in ("BK-PASS-SECRET", "DBPASS-SECRET"):
            assert secret not in log_text
            assert secret not in proc.stdout
            assert secret not in proc.stderr

    def test_pg_dump_falls_back_to_database_url_when_unset(self, make_env):
        cfg = make_env(transport="none")
        cfg["env"].pop("BACKUP_DATABASE_URL", None)

        proc = self._run_with_recording_pg_dump(cfg)
        assert proc.returncode == 0, proc.stdout + proc.stderr

        tokens = (cfg["marker_dir"] / "pg_dump.argv").read_text().splitlines()
        assert self._flag_value(tokens, "-h") == "localhost"
        assert self._flag_value(tokens, "-p") == "5432"
        assert self._flag_value(tokens, "-U") == "backup_user"
        assert self._flag_value(tokens, "-d") == "membership_db"
        pgpassword = (cfg["marker_dir"] / "pg_dump.pgpassword").read_text()
        assert pgpassword == "DBPASS-SECRET"


class TestSmbFailureReportsRealExitCode:
    """Locks real-rc propagation for the SMB transport: smbclient's own exit
    code MUST reach the WARNING log line, never masked to rc=0 by the
    if-construct bug. The failure stays warn-only and the SMB_PASS canary
    must never reach the log.
    """

    def test_smb_failure_logs_real_rc_and_hides_secret(self, make_env):
        cfg = make_env(transport="smb", with_smbclient=True)
        env = cfg["env"]
        env["SMB_SHARE"] = "//host/share"
        env["SMB_USER"] = "smbuser"
        env["SMB_PASS"] = "SMB-SECRET-TOKEN"
        env["SMB_PATH"] = "backups"

        # Replace the fixture's generic smbclient mock with the rc=7 one.
        bin_dir = Path(env["PATH"].split(":")[0])
        _write_exec(bin_dir / "smbclient", _MOCK_SMBCLIENT_RC7)

        proc = subprocess.run(
            ["bash", str(BACKUP_SH)], env=env, capture_output=True, text=True
        )
        # Warn-only: the overall backup still succeeds.
        assert proc.returncode == 0, proc.stdout + proc.stderr

        log_text = cfg["log_file"].read_text()

        # smbclient's real exit code reached the warning, unmasked.
        assert (
            "rc=7" in log_text
        ), f"real smbclient rc masked (if-construct bug?):\n{log_text}"

        # Credential isolation: the canary never reached the log.
        assert "SMB-SECRET-TOKEN" not in log_text, "SMB_PASS leaked into backup log"


class TestFailedRemoteNeverRemovesLocalArtifacts:
    """Spec: backup-remote-config/spec.md 'Probe failure MUST NOT alter local
    backups' + remote-backup isolation contract (correction #3).

    Any rc!=0 from remote_push (missing tool / unreachable host / tool failure)
    MUST leave seeded + freshly produced local dumps, tarballs, and checksums
    byte-identical and count-identical, retention MUST still run, and the
    overall backup MUST exit 0 (warn-only).
    """

    @pytest.mark.parametrize("transport", ["smb", "sftp", "ftp", "rsync", "nfs"])
    def test_failed_push_preserves_local_artifacts(self, make_env, transport):
        cfg = make_env(transport=transport, with_smbclient=(transport == "smb"))
        env = cfg["env"]

        # Configure every transport so each reaches its own tool/branch, then
        # fails (mocked tools exit non-zero; nfs points at a missing mount).
        env["SMB_SHARE"] = "//host/share"
        env["SMB_USER"] = "smbuser"
        env["SMB_PASS"] = "SMB-SECRET"
        env["SMB_PATH"] = "backups"
        env["SFTP_HOST"] = "remote.invalid"
        env["SFTP_PORT"] = "22"
        env["SFTP_USER"] = "u"
        env["SFTP_PATH"] = "/bkp"
        env["SSHPASS"] = "SSHP-SECRET"
        env["FTP_HOST"] = "remote.invalid"
        env["FTP_PORT"] = "21"
        env["FTP_USER"] = "u"
        env["FTP_PASS"] = "FTPP-SECRET"
        env["RSYNC_HOST"] = "remote.invalid"
        env["RSYNC_PATH"] = "/srv/bkp"
        env["NFS_MOUNT"] = "/no/such/mount/anywhere"

        # Seed a RECENT artifact (retention-safe) that must survive untouched,
        # plus an OLD one that retention MUST remove.
        recent_dump = _seed_recent(
            cfg["backup_dir"],
            "db_backup_20260101_000000.dump",
            b"precious-recent-dump",
        )
        recent_tar = _seed_recent(
            cfg["backup_dir"],
            "biometric_backup_20260101_000000.tar.gz",
            b"precious-recent-tar",
        )
        old_artifact = _seed_old_artifact(cfg["backup_dir"])
        run_start = time.time()

        proc = subprocess.run(
            ["bash", str(BACKUP_SH)], env=env, capture_output=True, text=True
        )
        # Warn-only: local backup + retention complete despite the remote failure.
        assert proc.returncode == 0, (
            f"{transport}: backup.sh exited {proc.returncode}\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

        # Seeded recent artifacts survive byte-identical.
        assert recent_dump.exists(), f"{transport}: seeded dump was removed"
        assert recent_dump.read_bytes() == b"precious-recent-dump"
        assert recent_tar.exists(), f"{transport}: seeded tar was removed"
        assert recent_tar.read_bytes() == b"precious-recent-tar"

        # Fresh artifacts were produced this run.
        fresh_dumps = [
            p
            for p in cfg["backup_dir"].glob("db_backup_*.dump")
            if p.stat().st_mtime >= run_start
        ]
        assert fresh_dumps, f"{transport}: no fresh .dump produced"
        fresh_checksums = [
            p
            for p in cfg["backup_dir"].glob("checksums_*.txt")
            if p.stat().st_mtime >= run_start
        ]
        assert fresh_checksums, f"{transport}: no fresh checksums produced"

        # Retention removed the old artifact.
        assert not old_artifact.exists(), f"{transport}: retention did not run"

        # The fresh dump is distinct from the seeded recent one (count grew).
        all_dumps = list(cfg["backup_dir"].glob("db_backup_*.dump"))
        assert recent_dump in all_dumps
        assert len(all_dumps) >= 2, f"{transport}: fresh dump not produced distinctly"
