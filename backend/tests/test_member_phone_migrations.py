"""Migration coverage for non-unique member contact phones."""

import logging
import uuid
from pathlib import Path
from unittest.mock import Mock

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from core.config import settings

BACKEND_ROOT = Path(__file__).resolve().parents[1]
LEGACY_REVISION = "5a4b3c2d1e0f"
# The revision that drops the legacy unique phone index — the subject of this
# module. Tracked separately from the chain head so that adding an unrelated
# migration moves only HEAD_REVISION below.
PHONE_DROP_REVISION = "6b5c4d3e2f1a"
HEAD_REVISION = "8d7e6f5a4b3c"


@pytest.fixture(autouse=True)
def _isolate_alembic_logging():
    """Restore logger state after in-process Alembic commands.

    alembic/env.py calls logging.config.fileConfig, which disables
    existing loggers by default. Without this, later startup-check
    tests in the same pytest process see disabled loggers.
    """
    manager = logging.Logger.manager
    snapshot = [
        (name, logger.disabled, logger.level, logger.propagate)
        for name, logger in manager.loggerDict.items()
        if isinstance(logger, logging.Logger)
    ]
    root_level = logging.root.level
    yield
    for name, disabled, level, propagate in snapshot:
        logger = logging.getLogger(name)
        logger.disabled = disabled
        logger.setLevel(level)
        logger.propagate = propagate
    logging.root.setLevel(root_level)


def _config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return config


@pytest.fixture(autouse=True)
def _ignore_deploy_migration_role(monkeypatch):
    """Keep these tests on their own throwaway database.

    alembic/env.py prefers MIGRATE_DATABASE_URL (the owning role used at deploy
    time) over DATABASE_URL. If a shell has the deploy env file sourced, that
    would silently point these migrations at the REAL database instead of the
    per-test one built below.
    """
    monkeypatch.delenv("MIGRATE_DATABASE_URL", raising=False)


@pytest.fixture
def migration_database():
    source_url = make_url(settings.DATABASE_URL)
    database_name = f"member_phone_migration_{uuid.uuid4().hex}"
    admin = create_engine(
        source_url.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))

    target_url = source_url.set(database=database_name)
    yield target_url.render_as_string(hide_password=False)

    with admin.connect() as connection:
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :database_name AND pid <> pg_backend_pid()"
            ),
            {"database_name": database_name},
        )
        connection.execute(text(f'DROP DATABASE "{database_name}"'))
    admin.dispose()


def _index_exists(engine) -> bool:
    with engine.connect() as connection:
        return (
            connection.scalar(text("SELECT to_regclass('ix_members_phone_unique')"))
            is not None
        )


def test_revision_chain_and_migration_operation_contracts(monkeypatch):
    script = ScriptDirectory.from_config(_config())
    legacy = script.get_revision(LEGACY_REVISION)
    successor = script.get_revision(PHONE_DROP_REVISION)

    # Exactly one head: a second head means two migrations claim the same
    # parent and `upgrade head` becomes ambiguous.
    assert script.get_heads() == [HEAD_REVISION]
    assert legacy is not None and legacy.down_revision == "e1f2a3b4c5d6"
    assert successor is not None and successor.down_revision == LEGACY_REVISION

    legacy_op = Mock()
    monkeypatch.setattr(legacy.module, "op", legacy_op, raising=False)
    legacy.module.upgrade()
    legacy.module.downgrade()
    assert legacy_op.mock_calls == []

    successor_op = Mock()
    monkeypatch.setattr(successor.module, "op", successor_op)
    successor.module.upgrade()
    successor_op.execute.assert_called_once_with(
        "DROP INDEX IF EXISTS ix_members_phone_unique"
    )
    successor_op.reset_mock()
    successor.module.downgrade()
    assert successor_op.mock_calls == []


def test_production_path_preserves_synthetic_duplicate_cardinalities(
    migration_database, monkeypatch
):
    monkeypatch.setattr(settings, "DATABASE_URL", migration_database)
    config = _config()
    command.upgrade(config, "f0786144f6c0")
    engine = create_engine(migration_database)
    phones = ["555-1001", "555-1001", "555-2002", "555-2002", "555-2002"]
    rows = [
        {
            "id": uuid.uuid4(),
            "first_name": f"Synthetic{index}",
            "last_name": "Member",
            "email": f"synthetic{index}@example.test",
            "phone": phone,
        }
        for index, phone in enumerate(phones)
    ]
    insert = text(
        "INSERT INTO members (id, first_name, last_name, email, phone) "
        "VALUES (:id, :first_name, :last_name, :email, :phone)"
    )
    grouped = text("SELECT phone, count(*) FROM members GROUP BY phone ORDER BY phone")
    with engine.begin() as connection:
        connection.execute(insert, rows)
        before_count = connection.scalar(text("SELECT count(*) FROM members"))
        before_groups = dict(connection.execute(grouped).all())

    command.upgrade(config, "head")

    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM members")) == before_count
        assert dict(connection.execute(grouped).all()) == before_groups
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            HEAD_REVISION
        )
    assert before_groups == {"555-1001": 2, "555-2002": 3}
    assert not _index_exists(engine)
    engine.dispose()


def test_stamped_dev_path_drops_legacy_index_and_is_idempotent(
    migration_database, monkeypatch
):
    monkeypatch.setattr(settings, "DATABASE_URL", migration_database)
    config = _config()
    command.upgrade(config, "e1f2a3b4c5d6")
    engine = create_engine(migration_database)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE UNIQUE INDEX ix_members_phone_unique ON members (phone) "
                "WHERE phone IS NOT NULL"
            )
        )
    command.stamp(config, LEGACY_REVISION)
    assert _index_exists(engine)

    command.upgrade(config, "head")
    assert not _index_exists(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO members (id, first_name, last_name, phone) VALUES "
                "(:first_id, 'First', 'Member', '555-3003'), "
                "(:second_id, 'Second', 'Member', '555-3003')"
            ),
            {"first_id": uuid.uuid4(), "second_id": uuid.uuid4()},
        )

    command.downgrade(config, LEGACY_REVISION)
    assert not _index_exists(engine)
    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM members WHERE phone = '555-3003'")
            )
            == 2
        )
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            HEAD_REVISION
        )
    assert not _index_exists(engine)
    engine.dispose()
