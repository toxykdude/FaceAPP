"""Tests for the dedicated migration-role connection URL.

Migrations need DDL authority; the runtime role deliberately has none. The
runtime role (``backend_app``) owns no tables precisely so that a compromised
application credential cannot DROP a table or run
``ALTER TABLE ... DISABLE ROW LEVEL SECURITY`` — which would neuter the RLS that
isolates portal members from each other's biometric and payment records. Only 1
of the 13 RLS-enabled tables sets FORCE ROW LEVEL SECURITY, so a table owner
bypasses RLS on the other 12.

Alembic therefore connects as a separate owning role via
``MIGRATE_DATABASE_URL``, mirroring how ``BACKUP_DATABASE_URL`` already
overrides the runtime URL for pg_dump (see api/system.py::_resolve_pg_dump_url
and scripts/backup.sh).
"""

from core.config import resolve_migration_database_url, settings


class TestMigrationUrlResolution:
    def test_prefers_the_migration_role_when_configured(self, monkeypatch):
        monkeypatch.setenv("MIGRATE_DATABASE_URL", "postgresql://migrator@/db")
        monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://runtime@/db")

        assert resolve_migration_database_url() == "postgresql://migrator@/db"

    def test_falls_back_to_the_runtime_url_when_unset(self, monkeypatch):
        """Local dev and CI connect as a role that already owns the schema, so
        the fallback must keep working with no extra configuration."""
        monkeypatch.delenv("MIGRATE_DATABASE_URL", raising=False)
        monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://runtime@/db")

        assert resolve_migration_database_url() == "postgresql://runtime@/db"

    def test_empty_migration_url_falls_back_rather_than_connecting_to_nothing(
        self, monkeypatch
    ):
        """An exported-but-empty variable is a misconfiguration, not an
        instruction to connect to an empty URL."""
        monkeypatch.setenv("MIGRATE_DATABASE_URL", "")
        monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://runtime@/db")

        assert resolve_migration_database_url() == "postgresql://runtime@/db"

    def test_reads_the_environment_on_every_call(self, monkeypatch):
        """The deploy sources /etc/faceapp/migrate-db.env into an already-running
        shell, so a value cached at import time would be the stale one."""
        monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://runtime@/db")
        monkeypatch.delenv("MIGRATE_DATABASE_URL", raising=False)
        assert resolve_migration_database_url() == "postgresql://runtime@/db"

        monkeypatch.setenv("MIGRATE_DATABASE_URL", "postgresql://migrator@/db")
        assert resolve_migration_database_url() == "postgresql://migrator@/db"


class TestAlembicEnvUsesTheResolver:
    def test_env_py_sets_the_url_from_the_resolver(self):
        """env.py must not read settings.DATABASE_URL directly — that is the
        runtime role, which cannot execute DDL against postgres-owned tables.
        """
        from pathlib import Path

        env_py = (
            Path(__file__).resolve().parents[1] / "alembic" / "env.py"
        ).read_text()

        assert "resolve_migration_database_url()" in env_py
        assert (
            'config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)'
            not in (env_py)
        )
