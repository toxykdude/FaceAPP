"""Strict-TDD coverage for portal payment integrity (change portal-secure-restore).

Scenario tags trace to:
- openspec/changes/portal-secure-restore/specs/payment-integrity/spec.md
- openspec/changes/portal-secure-restore/specs/customer-portal-runtime/spec.md

Unit 1 scope only: price CHECK + wompi_reference idempotency (model +
migration), PORTAL_INTERNAL_API_KEY + .env.example, webhook-renew rework
(design D1/D2/D4/D6/D9). Guest provisioning (Unit 2) lands in
test_guest_provisioning.py.
"""

import hashlib
import hmac
import json
import logging
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import redis as redis_lib

import api.portal as portal_module
from core.config import settings as app_settings
from core.database import Base
from models.member import Member
from models.membership import Membership, MembershipPlan
from models.sale import SalesTransaction

BACKEND_ROOT = Path(__file__).resolve().parents[1]
BASE_REVISION = "7c6d5e4f3a2b"
HEAD_REVISION = "8d7e6f5a4b3c"

INTEGRITY_SECRET = "test-integrity-secret"
INTERNAL_KEY = "test-internal-key"


# ---------------------------------------------------------------------------
# Shared harness
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_alembic_logging():
    """Restore logger state after in-process Alembic commands.

    alembic/env.py calls logging.config.fileConfig, which disables existing
    loggers by default. Without this, caplog-based tests later in the same
    pytest process see disabled loggers. (Pattern: test_member_phone_migrations.)
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


@pytest.fixture(autouse=True)
def _ignore_deploy_migration_role(monkeypatch):
    """Keep migration tests on their own throwaway database.

    alembic/env.py prefers MIGRATE_DATABASE_URL (the owning role used at
    deploy time) over DATABASE_URL; a sourced deploy env file must not
    silently point these migrations at the REAL database.
    """
    monkeypatch.delenv("MIGRATE_DATABASE_URL", raising=False)


@pytest.fixture
def scratch_database():
    """Throwaway Postgres database, dropped after the test."""
    source_url = make_url(app_settings.DATABASE_URL)
    database_name = f"portal_integrity_{uuid.uuid4().hex}"
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


def _alembic_config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return config


@pytest.fixture
def portal_redis():
    """Redis client tracking every pending key a test creates."""
    client = redis_lib.from_url(app_settings.REDIS_URL, decode_responses=True)
    created: list = []
    client._test_created_keys = created  # type: ignore[attr-defined]

    def track(key: str):
        if key not in created:
            created.append(key)

    client._test_track = track  # type: ignore[attr-defined]
    yield client
    for key in created:
        client.delete(key)
    client.close()


def _store_pending(client, *, plan, member, reference, amount=None):
    """Seed the Redis pending record the webhook must consume."""
    data = {
        "plan_id": str(plan.id),
        "member_id": str(member.id) if member is not None else None,
        "amount": str(amount if amount is not None else plan.price),
        "wompi_reference": reference,
    }
    key = f"pending-payment:{reference}"
    client.setex(key, 86400, json.dumps(data))
    client._test_track(key)  # type: ignore[attr-defined]
    return data


@pytest.fixture
def sample_plan(db_session):
    plan = MembershipPlan(
        name="Monthly Plan",
        duration_days=30,
        price=Decimal("50000"),
        is_active=True,
    )
    db_session.add(plan)
    db_session.flush()
    return plan


@pytest.fixture
def second_member(db_session):
    member = Member(
        first_name="Other",
        last_name="Member",
        email=f"other-{uuid.uuid4().hex[:8]}@example.com",
        phone="555-0200",
        status="active",
        consent_given_at=None,
    )
    db_session.add(member)
    db_session.flush()
    return member


def _cents(plan) -> int:
    return int(Decimal(str(plan.price)) * 100)


def _webhook_body(plan, member, reference, amount_in_cents, tx_id="tx-1"):
    body = {
        "wompi_reference": reference,
        "wompi_transaction_id": tx_id,
        "amount_in_cents": amount_in_cents,
    }
    if plan is not None:
        body["plan_id"] = str(plan.id)
    if member is not None:
        body["member_id"] = str(member.id)
    return body


def _signed(body: dict, secret: str = INTEGRITY_SECRET):
    raw = json.dumps(body).encode("utf-8")
    signature = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return raw, signature


def _post_webhook(client, body: dict, secret: str = INTEGRITY_SECRET, signature=None):
    raw, computed = _signed(body, secret)
    return client.post(
        "/api/portal/webhook-renew",
        headers={
            "X-Signature": signature if signature is not None else computed,
            "Content-Type": "application/json",
        },
        content=raw,
    )


@pytest.fixture
def webhook_env(monkeypatch):
    """Integrity secret + internal key configured, CV notify mocked."""
    monkeypatch.setattr(app_settings, "WOMPI_INTEGRITY_SECRET", INTEGRITY_SECRET)
    monkeypatch.setattr(app_settings, "PORTAL_INTERNAL_API_KEY", INTERNAL_KEY)
    mock_notify = AsyncMock()
    monkeypatch.setattr(portal_module, "notify_cv_invalidation", mock_notify)
    return mock_notify


def _count_rows(db_session, model, **filters):
    return db_session.query(model).filter_by(**filters).count()


# ---------------------------------------------------------------------------
# Phase 1 — Positive-Price Plan Constraint (task 1.1 / 1.2)
# ---------------------------------------------------------------------------


class TestPlanPriceConstraint:
    """Spec: Positive-Price Plan Constraint — model create_all parity."""

    def test_zero_price_plan_insert_is_rejected(self, scratch_database):
        """Scenario: Zero-price plan insert is rejected [pytest]."""
        engine = create_engine(scratch_database)
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        session.add(
            MembershipPlan(
                name="Free Plan", duration_days=30, price=Decimal("0"), is_active=True
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.close()
        engine.dispose()

    def test_negative_price_update_is_rejected(self, scratch_database):
        """Scenario: Negative-price update is rejected [pytest]."""
        engine = create_engine(scratch_database)
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        plan = MembershipPlan(
            name="Paid Plan", duration_days=30, price=Decimal("50000"), is_active=True
        )
        session.add(plan)
        session.commit()

        plan.price = Decimal("-1")
        with pytest.raises(IntegrityError):
            session.commit()
        session.close()
        engine.dispose()


class TestPriceCheckWompiReferenceMigration:
    """Migration 8d7e6f5a4b3c: price CHECK + wompi_reference backfill/UNIQUE."""

    def test_migration_chain_has_single_new_head(self):
        script = ScriptDirectory.from_config(_alembic_config())
        assert script.get_heads() == [HEAD_REVISION]
        head = script.get_revision(HEAD_REVISION)
        assert head.down_revision == BASE_REVISION

    def test_migration_docstring_records_trap20_mechanics(self):
        """Task 1.4: the migration documents the migrator-role runbook."""
        script = ScriptDirectory.from_config(_alembic_config())
        docstring = script.get_revision(HEAD_REVISION).module.__doc__ or ""
        assert "MIGRATE_DATABASE_URL" in docstring
        assert "alembic current" in docstring

    def test_upgrade_enforces_price_check_and_backfills_reference(
        self, scratch_database, monkeypatch
    ):
        monkeypatch.setattr(app_settings, "DATABASE_URL", scratch_database)
        config = _alembic_config()
        command.upgrade(config, BASE_REVISION)

        engine = create_engine(scratch_database)
        reference = f"ph-{uuid.uuid4().hex[:12]}"
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO members (id, first_name, last_name, email, phone) "
                    "VALUES (:id, 'Mig', 'Member', 'mig@example.test', '555-1234')"
                ),
                {"id": uuid.uuid4()},
            )
            connection.execute(
                text(
                    "INSERT INTO membership_plans (id, name, duration_days, price, "
                    "is_active, created_at, updated_at) VALUES "
                    "(:id, 'Plan', 30, 50000, true, now(), now())"
                ),
                {"id": uuid.uuid4()},
            )
            connection.execute(
                text(
                    "INSERT INTO sales_transactions (id, member_id, amount, "
                    "payment_method, invoice_number, created_at, notes) VALUES "
                    "(:id, (SELECT id FROM members LIMIT 1), 50000, 'card', "
                    ":invoice, now(), :notes)"
                ),
                [
                    {
                        "id": uuid.uuid4(),
                        "invoice": f"WOM-1-{uuid.uuid4().hex[:6]}",
                        "notes": f"Wompi ref: {reference} | Wompi tx: tx-9",
                    },
                    {
                        "id": uuid.uuid4(),
                        "invoice": f"WOM-2-{uuid.uuid4().hex[:6]}",
                        "notes": "cash sale, no wompi",
                    },
                ],
            )

        command.upgrade(config, HEAD_REVISION)

        with engine.connect() as connection:
            # Backfill: the wompi-noted row carries the reference, the other
            # stays NULL.
            backfilled = connection.scalar(
                text(
                    "SELECT wompi_reference FROM sales_transactions "
                    "WHERE notes LIKE 'Wompi ref:%'"
                )
            )
            assert backfilled == reference
            untouched = connection.scalar(
                text(
                    "SELECT wompi_reference FROM sales_transactions "
                    "WHERE notes = 'cash sale, no wompi'"
                )
            )
            assert untouched is None

            # UNIQUE index exists and aborts a duplicate reference.
            assert (
                connection.scalar(
                    text("SELECT to_regclass('ix_sales_transactions_wompi_reference')")
                )
                is not None
            )
        with engine.begin() as connection:
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        "INSERT INTO sales_transactions (id, member_id, amount, "
                        "payment_method, invoice_number, created_at, wompi_reference) VALUES "
                        "(:id, (SELECT id FROM members LIMIT 1), 1, 'card', "
                        ":invoice, now(), :reference)"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "invoice": f"WOM-3-{uuid.uuid4().hex[:6]}",
                        "reference": reference,
                    },
                )
        with engine.begin() as connection:
            # CHECK (price > 0) enforced by the migration.
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        "INSERT INTO membership_plans (id, name, duration_days, "
                        "price, is_active, created_at, updated_at) VALUES "
                        "(:id, 'Zero', 30, 0, true, now(), now())"
                    ),
                    {"id": uuid.uuid4()},
                )

        command.downgrade(config, BASE_REVISION)
        with engine.connect() as connection:
            # Downgrade drops CHECK/index only; column + data retained.
            assert (
                connection.scalar(
                    text("SELECT to_regclass('ix_sales_transactions_wompi_reference')")
                )
                is None
            )
            check_dropped = connection.scalar(
                text(
                    "SELECT count(*) FROM pg_constraint WHERE conname = " ":name",
                ),
                {"name": "ck_membership_plans_price_positive"},
            )
            assert check_dropped == 0
            retained = connection.scalar(
                text(
                    "SELECT wompi_reference FROM sales_transactions "
                    "WHERE notes LIKE 'Wompi ref:%'"
                )
            )
            assert retained == reference
        with engine.begin() as connection:
            # Price CHECK really is gone after downgrade (proves it existed).
            connection.execute(
                text(
                    "INSERT INTO membership_plans (id, name, duration_days, "
                    "price, is_active, created_at, updated_at) VALUES "
                    "(:id, 'Zero', 30, 0, true, now(), now())"
                ),
                {"id": uuid.uuid4()},
            )
        engine.dispose()

    def test_upgrade_fails_loud_listing_violating_rows(
        self, scratch_database, monkeypatch
    ):
        monkeypatch.setattr(app_settings, "DATABASE_URL", scratch_database)
        config = _alembic_config()
        command.upgrade(config, BASE_REVISION)

        engine = create_engine(scratch_database)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO membership_plans (id, name, duration_days, price, "
                    "is_active, created_at, updated_at) VALUES "
                    "(:id, 'Legacy Free', 30, 0, true, now(), now())"
                ),
                {"id": uuid.uuid4()},
            )
        engine.dispose()

        with pytest.raises(RuntimeError) as excinfo:
            command.upgrade(config, HEAD_REVISION)
        assert "Legacy Free" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Phase 1 — config + .env.example (task 1.3) / approval (task 1.4)
# ---------------------------------------------------------------------------


class TestPortalInternalApiKeySetting:
    def test_settings_expose_portal_internal_api_key(self):
        assert isinstance(app_settings.PORTAL_INTERNAL_API_KEY, str)


class TestEnvExamplePlaceholders:
    """Spec: Documented Portal Environment Placeholders."""

    REQUIRED_KEYS = (
        "MEMBER_PORTAL_DATABASE_URL",
        "WOMPI_PUBLIC_KEY",
        "WOMPI_INTEGRITY_SECRET",
        "EVOLUTION_API_URL",
        "EVOLUTION_API_KEY",
        "EVOLUTION_INSTANCE_NAME",
        "PORTAL_INTERNAL_API_KEY",
    )

    def test_placeholders_are_present_in_env_example(self):
        """Scenario: Placeholders are present in .env.example [pytest]."""
        env_path = BACKEND_ROOT / ".env.example"
        assert env_path.exists(), "backend/.env.example must exist"
        content = env_path.read_text()
        for key in self.REQUIRED_KEYS:
            assert f"{key}=" in content, f"{key} missing from .env.example"

        # Placeholder values only — never the live secret material.
        for live in (
            app_settings.SECRET_KEY,
            app_settings.WOMPI_INTEGRITY_SECRET or "",
            app_settings.PORTAL_INTERNAL_API_KEY or "",
        ):
            if live:
                assert live not in content


class TestIntegritySecretFailClosed:
    def test_missing_integrity_secret_fails_closed(self, monkeypatch):
        """Scenario: Missing integrity secret fails closed [pytest]."""
        monkeypatch.setattr(app_settings, "WOMPI_INTEGRITY_SECRET", None)
        assert portal_module.verify_wompi_signature(b"{}", "any-signature") is False


# ---------------------------------------------------------------------------
# Phase 2 — signature gate (task 2.1)
# ---------------------------------------------------------------------------


class TestWebhookSignatureGate:
    def test_forged_signature_changes_no_state(
        self, client, db_session, sample_member, sample_plan, portal_redis, webhook_env
    ):
        """Scenario: Forged signature changes no state [pytest]."""
        reference = f"ref-{uuid.uuid4().hex[:8]}"
        _store_pending(
            portal_redis, plan=sample_plan, member=sample_member, reference=reference
        )
        body = _webhook_body(sample_plan, sample_member, reference, _cents(sample_plan))

        before_m = _count_rows(db_session, Membership)
        before_t = _count_rows(db_session, SalesTransaction)

        resp = _post_webhook(client, body, signature="deadbeef")
        assert resp.status_code == 401, (resp.status_code, resp.text)

        assert _count_rows(db_session, Membership) == before_m
        assert _count_rows(db_session, SalesTransaction) == before_t
        webhook_env.assert_not_awaited()

    def test_missing_signature_is_rejected_before_lookup(self, client, webhook_env):
        """Scenario: Forged webhook is rejected [pytest]."""
        resp = client.post(
            "/api/portal/webhook-renew",
            headers={"X-Signature": ""},
            content=b"{}",
        )
        assert resp.status_code == 401
        webhook_env.assert_not_awaited()

    def test_missing_required_fields_is_rejected_422(
        self, client, sample_member, sample_plan, portal_redis, webhook_env
    ):
        """Task 2.1: reference/tx_id/amount_in_cents are all required."""
        reference = f"ref-{uuid.uuid4().hex[:8]}"
        _store_pending(
            portal_redis, plan=sample_plan, member=sample_member, reference=reference
        )

        no_cents = _webhook_body(sample_plan, sample_member, reference, 0)
        del no_cents["amount_in_cents"]
        resp = _post_webhook(client, no_cents)
        assert resp.status_code == 422, (resp.status_code, resp.text)

        no_tx = _webhook_body(
            sample_plan, sample_member, reference, _cents(sample_plan)
        )
        del no_tx["wompi_transaction_id"]
        resp = _post_webhook(client, no_tx)
        assert resp.status_code == 422, (resp.status_code, resp.text)

        no_ref = _webhook_body(sample_plan, sample_member, "", _cents(sample_plan))
        resp = _post_webhook(client, no_ref)
        assert resp.status_code == 422, (resp.status_code, resp.text)


# ---------------------------------------------------------------------------
# Phase 2 — pending consumption + idempotency (tasks 2.2, 2.4)
# ---------------------------------------------------------------------------


class TestPendingConsumption:
    def test_approved_webhook_commits_and_consumes_the_key(
        self, client, db_session, sample_member, sample_plan, portal_redis, webhook_env
    ):
        """Scenario: Approved webhook commits and consumes the key [pytest]."""
        reference = f"ref-{uuid.uuid4().hex[:8]}"
        _store_pending(
            portal_redis, plan=sample_plan, member=sample_member, reference=reference
        )
        body = _webhook_body(sample_plan, sample_member, reference, _cents(sample_plan))

        resp = _post_webhook(client, body)
        assert resp.status_code == 200, (resp.status_code, resp.text)
        data = resp.json()
        assert data["status"] == "success"

        # Membership + sale committed for the pending member at plan price.
        membership = (
            db_session.query(Membership)
            .filter_by(member_id=str(sample_member.id))
            .order_by(Membership.created_at.desc())
            .first()
        )
        assert membership is not None and membership.status == "active"
        sale = (
            db_session.query(SalesTransaction)
            .filter_by(membership_id=membership.id)
            .first()
        )
        assert sale is not None
        assert Decimal(str(sale.amount)) == Decimal(str(sample_plan.price))
        assert sale.wompi_reference == reference

        # Key consumed strictly after commit.
        assert portal_redis.get(f"pending-payment:{reference}") is None
        webhook_env.assert_awaited_once_with(str(sample_member.id))

    def test_replayed_reference_provisions_nothing_new(
        self, client, db_session, sample_member, sample_plan, portal_redis, webhook_env
    ):
        """Scenario: Replayed reference provisions nothing new [pytest].

        Replay AFTER consumption (no pending key): the DB reference hit must
        return already_processed, not a second membership.
        """
        reference = f"ref-{uuid.uuid4().hex[:8]}"
        _store_pending(
            portal_redis, plan=sample_plan, member=sample_member, reference=reference
        )
        first = _post_webhook(
            client,
            _webhook_body(sample_plan, sample_member, reference, _cents(sample_plan)),
        )
        assert first.status_code == 200

        replay = _post_webhook(
            client,
            _webhook_body(sample_plan, sample_member, reference, _cents(sample_plan)),
        )
        assert replay.status_code == 200, (replay.status_code, replay.text)
        assert replay.json()["status"] == "already_processed"

        assert _count_rows(db_session, SalesTransaction, wompi_reference=reference) == 1
        assert webhook_env.assert_awaited_once

    def test_concurrent_same_reference_unique_aborts_loser(
        self, client, db_session, sample_member, sample_plan, portal_redis, webhook_env
    ):
        """Task 2.4: the loser of a same-reference race hits the UNIQUE
        index, aborts, and reports already_processed — never two sales."""
        reference = f"ref-{uuid.uuid4().hex[:8]}"
        _store_pending(
            portal_redis, plan=sample_plan, member=sample_member, reference=reference
        )
        first = _post_webhook(
            client,
            _webhook_body(sample_plan, sample_member, reference, _cents(sample_plan)),
        )
        assert first.status_code == 200

        # Simulate the race window: the loser re-reads the pending key the
        # winner had not deleted yet.
        _store_pending(
            portal_redis, plan=sample_plan, member=sample_member, reference=reference
        )
        loser = _post_webhook(
            client,
            _webhook_body(sample_plan, sample_member, reference, _cents(sample_plan)),
        )
        assert loser.status_code == 200, (loser.status_code, loser.text)
        assert loser.json()["status"] == "already_processed"
        assert _count_rows(db_session, SalesTransaction, wompi_reference=reference) == 1

    def test_unknown_reference_provisions_nothing(
        self, client, db_session, sample_member, sample_plan, webhook_env, caplog
    ):
        """Scenario: Unknown reference provisions nothing [pytest] +
        Webhook without pending record is rejected [pytest] — with an alert."""
        reference = f"ref-{uuid.uuid4().hex[:8]}"
        before_m = _count_rows(db_session, Membership)
        before_t = _count_rows(db_session, SalesTransaction)

        with caplog.at_level(logging.ERROR, logger="api.portal"):
            resp = _post_webhook(
                client,
                _webhook_body(
                    sample_plan, sample_member, reference, _cents(sample_plan)
                ),
            )
        assert resp.status_code == 404, (resp.status_code, resp.text)
        assert reference in caplog.text

        assert _count_rows(db_session, Membership) == before_m
        assert _count_rows(db_session, SalesTransaction) == before_t
        webhook_env.assert_not_awaited()

    def test_failed_commit_retains_the_pending_key(
        self,
        client,
        db_session,
        sample_member,
        sample_plan,
        portal_redis,
        webhook_env,
        monkeypatch,
    ):
        """Scenario: Failed commit retains the pending key [pytest]."""
        reference = f"ref-{uuid.uuid4().hex[:8]}"
        _store_pending(
            portal_redis, plan=sample_plan, member=sample_member, reference=reference
        )

        def _boom():
            raise RuntimeError("simulated commit failure")

        monkeypatch.setattr(db_session, "commit", _boom)
        with pytest.raises(RuntimeError):
            _post_webhook(
                client,
                _webhook_body(
                    sample_plan, sample_member, reference, _cents(sample_plan)
                ),
            )

        db_session.rollback()
        assert portal_redis.get(f"pending-payment:{reference}") is not None
        assert _count_rows(db_session, SalesTransaction, wompi_reference=reference) == 0
        webhook_env.assert_not_awaited()

    def test_redis_member_id_is_authoritative_body_member_ignored(
        self,
        client,
        db_session,
        sample_member,
        second_member,
        sample_plan,
        portal_redis,
        webhook_env,
    ):
        """D9: body member_id is ignored; the pending record decides."""
        reference = f"ref-{uuid.uuid4().hex[:8]}"
        _store_pending(
            portal_redis, plan=sample_plan, member=sample_member, reference=reference
        )
        resp = _post_webhook(
            client,
            _webhook_body(sample_plan, second_member, reference, _cents(sample_plan)),
        )
        assert resp.status_code == 200, (resp.status_code, resp.text)

        sale = (
            db_session.query(SalesTransaction)
            .filter_by(wompi_reference=reference)
            .first()
        )
        assert sale is not None
        assert str(sale.member_id) == str(sample_member.id)

    def test_stale_body_plan_id_is_ignored_pending_is_authoritative(
        self, client, db_session, sample_member, sample_plan, portal_redis, webhook_env
    ):
        """D9: the plan comes from the pending record, not the body."""
        reference = f"ref-{uuid.uuid4().hex[:8]}"
        _store_pending(
            portal_redis, plan=sample_plan, member=sample_member, reference=reference
        )
        body = _webhook_body(None, sample_member, reference, _cents(sample_plan))
        body["plan_id"] = str(uuid.uuid4())  # stale/garbage — must be ignored
        resp = _post_webhook(client, body)
        assert resp.status_code == 200, (resp.status_code, resp.text)

        sale = (
            db_session.query(SalesTransaction)
            .filter_by(wompi_reference=reference)
            .first()
        )
        assert sale is not None
        assert str(sale.member_id) == str(sample_member.id)


# ---------------------------------------------------------------------------
# Phase 2 — amount gates (task 2.3)
# ---------------------------------------------------------------------------


class TestAmountGates:
    def test_amount_not_matching_the_pending_record_is_rejected(
        self,
        client,
        db_session,
        sample_member,
        sample_plan,
        portal_redis,
        webhook_env,
        caplog,
    ):
        """Scenario: Amount not matching the pending record is rejected [pytest]."""
        reference = f"ref-{uuid.uuid4().hex[:8]}"
        _store_pending(
            portal_redis,
            plan=sample_plan,
            member=sample_member,
            reference=reference,
            amount=Decimal("1.00"),  # tampered — plan.price is 50000
        )
        with caplog.at_level(logging.ERROR, logger="api.portal"):
            resp = _post_webhook(
                client,
                _webhook_body(
                    sample_plan, sample_member, reference, _cents(sample_plan)
                ),
            )
        assert resp.status_code == 400, (resp.status_code, resp.text)
        assert reference in caplog.text

        assert _count_rows(db_session, SalesTransaction, wompi_reference=reference) == 0
        # Key retained for retry/alerting.
        assert portal_redis.get(f"pending-payment:{reference}") is not None
        webhook_env.assert_not_awaited()

    def test_backend_underpayment_yields_no_membership(
        self,
        client,
        db_session,
        sample_member,
        sample_plan,
        portal_redis,
        webhook_env,
        caplog,
    ):
        """Scenario: Backend underpayment yields no membership [pytest]."""
        reference = f"ref-{uuid.uuid4().hex[:8]}"
        _store_pending(
            portal_redis, plan=sample_plan, member=sample_member, reference=reference
        )
        underpaid = _cents(sample_plan) - 100  # one peso short

        with caplog.at_level(logging.ERROR, logger="api.portal"):
            resp = _post_webhook(
                client, _webhook_body(sample_plan, sample_member, reference, underpaid)
            )
        assert resp.status_code == 400, (resp.status_code, resp.text)
        assert reference in caplog.text

        assert _count_rows(db_session, Membership, member_id=str(sample_member.id)) == 0
        assert _count_rows(db_session, SalesTransaction, wompi_reference=reference) == 0
        assert portal_redis.get(f"pending-payment:{reference}") is not None
        webhook_env.assert_not_awaited()

    def test_overpayment_is_accepted(
        self, client, db_session, sample_member, sample_plan, portal_redis, webhook_env
    ):
        """D4: overpayment forwards (tx >= plan price); underpayment never."""
        reference = f"ref-{uuid.uuid4().hex[:8]}"
        _store_pending(
            portal_redis, plan=sample_plan, member=sample_member, reference=reference
        )
        overpaid = _cents(sample_plan) + 5000
        resp = _post_webhook(
            client, _webhook_body(sample_plan, sample_member, reference, overpaid)
        )
        assert resp.status_code == 200, (resp.status_code, resp.text)
        assert _count_rows(db_session, SalesTransaction, wompi_reference=reference) == 1


# ---------------------------------------------------------------------------
# Phase 2 — internal key on pending reads (task 2.6)
# ---------------------------------------------------------------------------


class TestInternalKeyPendingReads:
    def _get(self, client, reference, key):
        headers = {"X-API-Key": key} if key is not None else {}
        return client.get(f"/api/portal/pending-payment/{reference}", headers=headers)

    def test_pending_read_with_the_internal_key_succeeds(
        self, client, sample_member, sample_plan, portal_redis, monkeypatch
    ):
        """Scenario: Pending read with the internal key succeeds [pytest]."""
        monkeypatch.setattr(app_settings, "PORTAL_INTERNAL_API_KEY", INTERNAL_KEY)
        reference = f"ref-{uuid.uuid4().hex[:8]}"
        _store_pending(
            portal_redis, plan=sample_plan, member=sample_member, reference=reference
        )

        resp = self._get(client, reference, INTERNAL_KEY)
        assert resp.status_code == 200, (resp.status_code, resp.text)
        data = resp.json()
        assert data["status"] == "found"
        assert data["wompi_reference"] == reference

    def test_pending_read_requires_the_internal_key(
        self, client, sample_member, sample_plan, portal_redis, monkeypatch
    ):
        """Scenario: Pending read requires the internal key [pytest]."""
        monkeypatch.setattr(app_settings, "PORTAL_INTERNAL_API_KEY", INTERNAL_KEY)
        reference = f"ref-{uuid.uuid4().hex[:8]}"
        _store_pending(
            portal_redis, plan=sample_plan, member=sample_member, reference=reference
        )

        assert self._get(client, reference, "wrong-key").status_code == 401
        assert self._get(client, reference, None).status_code == 401

    def test_secret_key_no_longer_authorizes_pending_reads(
        self, client, sample_member, sample_plan, portal_redis, monkeypatch
    ):
        """Scenario: SECRET_KEY no longer authorizes pending reads [pytest]."""
        monkeypatch.setattr(app_settings, "PORTAL_INTERNAL_API_KEY", INTERNAL_KEY)
        reference = f"ref-{uuid.uuid4().hex[:8]}"
        _store_pending(
            portal_redis, plan=sample_plan, member=sample_member, reference=reference
        )

        resp = self._get(client, reference, app_settings.SECRET_KEY)
        assert resp.status_code == 401, (resp.status_code, resp.text)

    def test_pending_read_with_only_secret_key_is_denied(self, client, monkeypatch):
        """Scenario: Pending read with only SECRET_KEY is denied [pytest]."""
        monkeypatch.setattr(app_settings, "PORTAL_INTERNAL_API_KEY", INTERNAL_KEY)
        resp = self._get(client, f"ref-{uuid.uuid4().hex[:8]}", app_settings.SECRET_KEY)
        assert resp.status_code == 401

    def test_unset_internal_key_denies_all_fail_closed(
        self, client, sample_member, sample_plan, portal_redis, monkeypatch
    ):
        """D2: unset/empty key → deny-all 401."""
        monkeypatch.setattr(app_settings, "PORTAL_INTERNAL_API_KEY", "")
        reference = f"ref-{uuid.uuid4().hex[:8]}"
        _store_pending(
            portal_redis, plan=sample_plan, member=sample_member, reference=reference
        )

        assert self._get(client, reference, INTERNAL_KEY).status_code == 401
        assert self._get(client, reference, app_settings.SECRET_KEY).status_code == 401

    def test_denials_do_not_disclose_reference_existence(
        self, client, sample_member, sample_plan, portal_redis, monkeypatch
    ):
        """D2: uniform 401 — identical response whether or not the ref exists."""
        monkeypatch.setattr(app_settings, "PORTAL_INTERNAL_API_KEY", INTERNAL_KEY)
        existing = f"ref-{uuid.uuid4().hex[:8]}"
        _store_pending(
            portal_redis, plan=sample_plan, member=sample_member, reference=existing
        )
        missing = f"ref-{uuid.uuid4().hex[:8]}"

        for key in ("wrong-key", app_settings.SECRET_KEY):
            resp_existing = self._get(client, existing, key)
            resp_missing = self._get(client, missing, key)
            assert resp_existing.status_code == 401
            assert (resp_existing.status_code, resp_existing.text) == (
                resp_missing.status_code,
                resp_missing.text,
            )


class TestNoSecretReachesClientResponses:
    def test_no_secret_reaches_a_client_response(
        self, client, sample_member, sample_plan, portal_redis, webhook_env
    ):
        """Scenario: No secret reaches a client response [pytest]."""
        reference = f"ref-{uuid.uuid4().hex[:8]}"
        _store_pending(
            portal_redis, plan=sample_plan, member=sample_member, reference=reference
        )

        responses = [
            _post_webhook(
                client,
                _webhook_body(
                    sample_plan, sample_member, reference, _cents(sample_plan)
                ),
            ),
            _post_webhook(client, {"wompi_reference": reference}, signature="bad"),
            client.get(
                f"/api/portal/pending-payment/{reference}",
                headers={"X-API-Key": INTERNAL_KEY},
            ),
            client.get(f"/api/portal/pending-payment/{reference}"),
        ]
        secrets = (
            INTEGRITY_SECRET,
            INTERNAL_KEY,
            app_settings.SECRET_KEY,
            app_settings.ENCRYPTION_KEY,
        )
        for resp in responses:
            for secret in secrets:
                assert secret not in resp.text
