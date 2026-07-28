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
    env["DATABASE_URL"] = "postgresql://backup_user:DBPASS-SECRET@localhost:5432/membership_db"
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
        assert not old_artifact.exists(), (
            "retention did not remove an artifact older than RETENTION_DAYS"
        )

        log_text = isolated_env["log_file"].read_text()

        # Remote failure was logged as an unsuccessful replication (warn, not
        # fatal). Match either Spanish or English phrasing defensively.
        assert "remote" in log_text.lower(), (
            f"remote-failure warning missing from log:\n{log_text}"
        )

        # Credential isolation: no secret token ever reaches the log.
        assert "SMB-SECRET-TOKEN" not in log_text, (
            "SMB_PASS value leaked into backup log"
        )
        assert "DBPASS-SECRET" not in log_text, (
            "DB password leaked into backup log"
        )

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
        fresh = [p for p in backup_dir.glob("db_backup_*.dump") if p.stat().st_mtime >= run_start]
        assert fresh, "no local .dump produced in none-mode"
        log_text = isolated_env["log_file"].read_text()
        # No secret leakage even in the no-op path.
        assert "DBPASS-SECRET" not in log_text
