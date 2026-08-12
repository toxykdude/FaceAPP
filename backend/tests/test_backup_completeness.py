"""Completeness contract for ``scripts/backup.sh``.

A backup is only useful if restoring it reproduces the platform: every member,
every membership, and the face data that lets the kiosk recognize people at the
door. Two production defects motivated this suite (both verified 2026-08-12):

1. ``backup.sh`` archived ``$DATA_DIR/biometric_data``, a directory that does
   not exist on any deployed host. The real face data lives in
   ``$DATA_DIR/member-photos``. The script logged "directory not found,
   skipping" and exited 0, so every backup silently omitted member photos —
   and the existing isolation suite never caught it because its fixture
   *created* ``biometric_data`` before running.

2. On an RLS-enforced database a role without BYPASSRLS makes ``pg_dump``
   abort partway through, leaving a truncated archive. Nothing downstream ever
   read the archive back, so a 57 KB corpse passed for a backup.

The tests below therefore assert on the CONTENTS of what was produced, never
merely that a file appeared. ``$DATA_DIR/snapshots`` (~1 GB of access-event
camera frames on production) is deliberately excluded: it is disposable
evidence, not state a migration needs.
"""

import os
import subprocess
import tarfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKUP_SH = REPO_ROOT / "scripts" / "backup.sh"

# Tables without which a restored database is not the gym: who the members
# are, what they have paid for, and the encrypted face templates.
MIGRATION_CRITICAL_TABLES = ("members", "memberships", "biometric_templates")


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


# Honours -f by writing a minimal custom-format-looking archive.
_MOCK_PG_DUMP = """#!/usr/bin/env bash
f=""; prev=""
for a in "$@"; do
  if [ "$prev" = "-f" ]; then f="$a"; fi
  prev="$a"
done
[ -z "$f" ] && { echo 'mock pg_dump: no -f target' >&2; exit 1; }
printf 'PGDMP mock-dump-body' > "$f"
exit 0
"""

# A pg_dump that aborts on RLS the way production did: partial file, rc=1.
_MOCK_PG_DUMP_RLS_ABORT = """#!/usr/bin/env bash
f=""; prev=""
for a in "$@"; do
  if [ "$prev" = "-f" ]; then f="$a"; fi
  prev="$a"
done
printf 'PGDMP truncated' > "$f"
echo 'pg_dump: error: query failed: ERROR:  query would be affected by row-level security policy for table "access_events"' >&2
exit 1
"""

# A healthy archive: the TOC lists DATA for every migration-critical table AND
# the archive reads through (`-f`) cleanly.
_MOCK_PG_RESTORE_COMPLETE = """#!/usr/bin/env bash
if [ "$1" = "-l" ]; then
cat <<'TOC'
;
; Archive created at 2026-08-12 18:00:00 UTC
;
215; 1259 25741 TABLE public members membership
3402; 0 25741 TABLE DATA public members membership
3403; 0 25747 TABLE DATA public memberships membership
3404; 0 25755 TABLE DATA public biometric_templates membership
TOC
exit 0
fi
# read-through (-f /dev/null): archive is whole
exit 0
"""

# THE production archive, reproduced from measurements taken on LXC 114 on
# 2026-08-12: pg_dump aborted mid-COPY leaving 56,941 bytes, yet `pg_restore
# -l` returns rc=0 and still lists TABLE DATA for every critical table —
# because pg_dump writes the entire TOC before streaming any row. Only reading
# the archive THROUGH exposes it. A mock that omitted the tables from the TOC
# would be testing a failure mode that does not occur.
_MOCK_PG_RESTORE_TRUNCATED = """#!/usr/bin/env bash
if [ "$1" = "-l" ]; then
cat <<'TOC'
;
; Archive created at 2026-08-12 18:00:00 UTC
;
215; 1259 25741 TABLE public members membership
3402; 0 25741 TABLE DATA public members membership
3403; 0 25747 TABLE DATA public memberships membership
3404; 0 25755 TABLE DATA public biometric_templates membership
TOC
exit 0
fi
echo 'pg_restore: error: could not read from input file: end of file' >&2
exit 1
"""

# A schema-only dump: reads through fine, but carries no rows. This is what
# the TOC check exists for.
_MOCK_PG_RESTORE_SCHEMA_ONLY = """#!/usr/bin/env bash
if [ "$1" = "-l" ]; then
cat <<'TOC'
;
; Archive created at 2026-08-12 18:00:00 UTC
;
215; 1259 25741 TABLE public members membership
216; 1259 25747 TABLE public memberships membership
217; 1259 25755 TABLE public biometric_templates membership
TOC
exit 0
fi
exit 0
"""


@pytest.fixture
def backup_env(tmp_path):
    """An isolated backup run whose DATA_DIR mirrors a REAL deployed host.

    Critically: no ``biometric_data`` directory is created, because no deployed
    host has one. Tests that want it opt in explicitly.
    """

    def _build(
        *,
        with_member_photos=True,
        with_biometric_data=False,
        with_snapshots=True,
        pg_dump=_MOCK_PG_DUMP,
        pg_restore=_MOCK_PG_RESTORE_COMPLETE,
        install_pg_restore=True,
    ):
        backup_dir = tmp_path / "backups"
        data_dir = tmp_path / "data"
        log_file = tmp_path / "backup.log"
        bin_dir = tmp_path / "bin"

        for d in (backup_dir, data_dir, bin_dir):
            d.mkdir(parents=True, exist_ok=True)

        if with_member_photos:
            photos = data_dir / "member-photos"
            photos.mkdir()
            (photos / "42.jpg").write_bytes(b"\xff\xd8\xff-member-42-face")
            (photos / "43.jpg").write_bytes(b"\xff\xd8\xff-member-43-face")
        if with_biometric_data:
            bio = data_dir / "biometric_data"
            bio.mkdir()
            (bio / "template.bin").write_bytes(b"\x00\x01\x02")
        if with_snapshots:
            snaps = data_dir / "snapshots"
            snaps.mkdir()
            (snaps / "event-1.jpg").write_bytes(b"\xff\xd8\xff-camera-frame")

        _write_exec(bin_dir / "pg_dump", pg_dump)
        if install_pg_restore:
            _write_exec(bin_dir / "pg_restore", pg_restore)
            pg_restore_bin = "pg_restore"
        else:
            # PATH cannot hide the binary (the host really has postgresql-client
            # and tar/gzip need /usr/bin), so simulate absence through the
            # documented override instead.
            pg_restore_bin = str(tmp_path / "absent" / "pg_restore")

        env = os.environ.copy()
        # A clean PATH so an absent mock really is absent (no system fallback).
        env["PATH"] = f"{bin_dir}:/usr/bin:/bin"
        env["BACKUP_DIR"] = str(backup_dir)
        env["DATA_DIR"] = str(data_dir)
        env["LOG_FILE"] = str(log_file)
        env["ENV_FILE"] = str(tmp_path / "no-such-env")
        env["RETENTION_DAYS"] = "30"
        env["DATABASE_URL"] = (
            "postgresql://backup_user:DBPASS-SECRET@localhost:5432/membership_db"
        )
        env["BACKUP_REMOTE_TYPE"] = "none"
        env["PG_RESTORE_BIN"] = pg_restore_bin

        return {
            "env": env,
            "backup_dir": backup_dir,
            "data_dir": data_dir,
            "log_file": log_file,
        }

    return _build


def _run(cfg):
    return subprocess.run(
        ["bash", str(BACKUP_SH)],
        env=cfg["env"],
        capture_output=True,
        text=True,
    )


def _face_archive(backup_dir: Path) -> Path:
    matches = sorted(backup_dir.glob("biometric_backup_*.tar.gz"))
    assert matches, f"no face-data archive produced in {backup_dir}"
    return matches[-1]


def _members(archive: Path) -> list:
    with tarfile.open(archive, "r:gz") as tf:
        return tf.getnames()


class TestFaceDataIsActuallyBackedUp:
    """The archive must contain the face data a migration needs."""

    def test_member_photos_are_archived_on_a_realistic_host(self, backup_env):
        """No biometric_data dir (as on every deployed host) — photos still ship."""
        cfg = backup_env(with_member_photos=True, with_biometric_data=False)
        proc = _run(cfg)
        assert proc.returncode == 0, proc.stdout + proc.stderr

        names = _members(_face_archive(cfg["backup_dir"]))
        assert any(
            n.endswith("member-photos/42.jpg") for n in names
        ), f"member photos missing from the face-data archive: {names}"
        assert any(n.endswith("member-photos/43.jpg") for n in names)

    def test_archived_photo_bytes_round_trip(self, backup_env):
        """Extraction must return the original file, not an empty placeholder."""
        cfg = backup_env()
        assert _run(cfg).returncode == 0

        with tarfile.open(_face_archive(cfg["backup_dir"]), "r:gz") as tf:
            entry = next(n for n in tf.getnames() if n.endswith("member-photos/42.jpg"))
            extracted = tf.extractfile(entry).read()
        assert extracted == b"\xff\xd8\xff-member-42-face"

    def test_legacy_biometric_data_still_archived_when_present(self, backup_env):
        """Hosts that DO have biometric_data must not lose it to the new path."""
        cfg = backup_env(with_member_photos=True, with_biometric_data=True)
        assert _run(cfg).returncode == 0

        names = _members(_face_archive(cfg["backup_dir"]))
        assert any(n.endswith("biometric_data/template.bin") for n in names), names
        assert any(n.endswith("member-photos/42.jpg") for n in names), names

    def test_access_event_snapshots_are_excluded(self, backup_env):
        """~1 GB of camera frames per host is disposable evidence, not state."""
        cfg = backup_env(with_snapshots=True)
        assert _run(cfg).returncode == 0

        names = _members(_face_archive(cfg["backup_dir"]))
        assert not any(
            "snapshots/" in n for n in names
        ), f"access-event snapshots leaked into the backup: {names}"

    def test_missing_face_data_warns_loudly_but_is_not_fatal(self, backup_env):
        """A fresh install has no photos yet; the DB backup must still succeed."""
        cfg = backup_env(with_member_photos=False, with_biometric_data=False)
        proc = _run(cfg)
        assert proc.returncode == 0, proc.stdout + proc.stderr

        log_text = cfg["log_file"].read_text()
        assert "WARNING" in log_text
        assert (
            "member-photos" in log_text
        ), f"the warning must name the directory it expected:\n{log_text}"


class TestDumpIsVerifiedBeforeBeingCalledABackup:
    """Read the archive back; a file that exists is not a backup."""

    def test_truncated_dump_fails_the_backup(self, backup_env):
        """The production 57 KB scenario must exit non-zero, not 'successfully'.

        Note the mock: its TOC is HEALTHY and lists every critical table. That
        is what the real truncated archive does, so a check that only reads the
        TOC passes it. Only the end-to-end read fails.
        """
        cfg = backup_env(pg_restore=_MOCK_PG_RESTORE_TRUNCATED)
        proc = _run(cfg)

        assert proc.returncode != 0, (
            "a truncated archive with a healthy-looking TOC was reported as a "
            "successful backup — this is the production regression"
        )
        combined = proc.stdout + proc.stderr + cfg["log_file"].read_text()
        assert "TRUNCATED" in combined.upper(), combined

    def test_schema_only_dump_fails_the_backup(self, backup_env):
        """Reads through cleanly, carries no rows — caught by the TOC check."""
        cfg = backup_env(pg_restore=_MOCK_PG_RESTORE_SCHEMA_ONLY)
        proc = _run(cfg)

        assert proc.returncode != 0, "a row-less dump was accepted as a backup"
        combined = proc.stdout + proc.stderr + cfg["log_file"].read_text()
        for table in MIGRATION_CRITICAL_TABLES:
            assert table in combined, f"{table} not named in the failure: {combined}"

    def test_pg_dump_abort_is_fatal(self, backup_env):
        cfg = backup_env(pg_dump=_MOCK_PG_DUMP_RLS_ABORT)
        proc = _run(cfg)
        assert proc.returncode != 0, "an aborted pg_dump did not fail the backup"

    def test_complete_dump_passes_verification(self, backup_env):
        cfg = backup_env(pg_restore=_MOCK_PG_RESTORE_COMPLETE)
        proc = _run(cfg)
        assert proc.returncode == 0, proc.stdout + proc.stderr

        log_text = cfg["log_file"].read_text()
        assert "verif" in log_text.lower(), f"verification not logged:\n{log_text}"

    def test_missing_pg_restore_warns_rather_than_failing(self, backup_env):
        """Absent tooling must not destroy an otherwise-good backup."""
        cfg = backup_env(install_pg_restore=False)
        proc = _run(cfg)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "pg_restore" in cfg["log_file"].read_text()

    def test_verification_never_leaks_the_db_password(self, backup_env):
        cfg = backup_env(pg_restore=_MOCK_PG_RESTORE_TRUNCATED)
        proc = _run(cfg)
        blob = proc.stdout + proc.stderr + cfg["log_file"].read_text()
        assert "DBPASS-SECRET" not in blob


class TestFaceDataRoundTrip:
    """The only question that matters: does restoring bring the faces back?

    ``restore.sh`` extracts the face archive with ``tar -xzf <archive> -C
    $DATA_DIR``. These tests perform that exact extraction against a clean
    target, so the backup and restore halves cannot drift apart — a change to
    either side that breaks migration fails here.
    """

    def test_photos_land_at_the_path_the_api_serves_them_from(
        self, backup_env, tmp_path
    ):
        cfg = backup_env(with_member_photos=True, with_biometric_data=False)
        assert _run(cfg).returncode == 0

        restored = tmp_path / "restored-data-dir"
        restored.mkdir()
        subprocess.run(
            ["tar", "-xzf", str(_face_archive(cfg["backup_dir"])), "-C", str(restored)],
            check=True,
        )

        # api/members.py serves /var/lib/powerhouse/member-photos/{id}.jpg —
        # the archive must reproduce that layout relative to DATA_DIR, not a
        # nested or flattened variant.
        photo = restored / "member-photos" / "42.jpg"
        assert photo.exists(), (
            "restored tree does not contain member-photos/42.jpg; "
            f"got {[str(p.relative_to(restored)) for p in restored.rglob('*')]}"
        )
        assert photo.read_bytes() == b"\xff\xd8\xff-member-42-face"

    def test_round_trip_carries_both_directories_when_both_exist(
        self, backup_env, tmp_path
    ):
        cfg = backup_env(with_member_photos=True, with_biometric_data=True)
        assert _run(cfg).returncode == 0

        restored = tmp_path / "restored-both"
        restored.mkdir()
        subprocess.run(
            ["tar", "-xzf", str(_face_archive(cfg["backup_dir"])), "-C", str(restored)],
            check=True,
        )

        assert (restored / "member-photos" / "42.jpg").exists()
        assert (restored / "biometric_data" / "template.bin").read_bytes() == (
            b"\x00\x01\x02"
        )
