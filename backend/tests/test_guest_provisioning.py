"""Strict-TDD coverage for guest purchase provisioning (change portal-secure-restore).

Scenario tags trace to:
- openspec/changes/portal-secure-restore/specs/guest-purchase-provisioning/spec.md

Unit 2 scope: canonical-phone service (phase 3), guest pending endpoint
(design D10, phase 4), webhook guest provisioning branch (design D5/D9,
phase 4). Unit 1 payment-integrity coverage lives in
test_portal_webhook_integrity.py; the Pages half (vitest) is Unit 3.
"""

import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

import redis as redis_lib

import api.portal as portal_module
import api.portal_auth as portal_auth_module
from core.config import settings as app_settings
from models.member import Member
from models.membership import Membership, MembershipPlan
from models.sale import SalesTransaction

INTEGRITY_SECRET = "test-integrity-secret"
INTERNAL_KEY = "test-internal-key"
CV_TEST_KEY = "cv-test-key-42"

# Canonical phone used across guest tests: 57 + 10 digits starting with 3.
GUEST_PHONE_RAW = "300 111 2233"
GUEST_PHONE = "573001112233"
GUEST_NAME = "Maria Fernanda Lopez"
GUEST_EMAIL = "maria.fernanda@example.com"


def _guest_reference() -> str:
    """A reference matching the Pages signature format (D10 regex)."""
    return f"PH-guest-{uuid.uuid4().hex[:6]}-{int(time.time())}-0a1b2c"


@pytest.fixture
def portal_redis():
    """Redis client tracking every pending/lock key a test creates."""
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


@pytest.fixture
def gym_plan(db_session):
    plan = MembershipPlan(
        name="Mensual Gimnasio",
        duration_days=30,
        price=Decimal("69900"),
        is_active=True,
    )
    db_session.add(plan)
    db_session.flush()
    return plan


@pytest.fixture
def webhook_env(monkeypatch):
    """Integrity secret + internal key configured, CV notify mocked."""
    monkeypatch.setattr(app_settings, "WOMPI_INTEGRITY_SECRET", INTEGRITY_SECRET)
    monkeypatch.setattr(app_settings, "PORTAL_INTERNAL_API_KEY", INTERNAL_KEY)
    mock_notify = AsyncMock()
    monkeypatch.setattr(portal_module, "notify_cv_invalidation", mock_notify)
    return mock_notify


def _cents(plan) -> int:
    return int(Decimal(str(plan.price)) * 100)


def _store_guest_pending(
    client,
    *,
    plan,
    reference,
    name=GUEST_NAME,
    phone=GUEST_PHONE,
    email=GUEST_EMAIL,
    amount=None,
):
    """Seed the v2 GUEST pending record the webhook must provision."""
    data = {
        "v": 2,
        "plan_id": str(plan.id),
        "member_id": None,
        "guest_name": name,
        "guest_phone": phone,
        "guest_email": email,
        "amount": str(amount if amount is not None else plan.price),
        "wompi_reference": reference,
    }
    key = f"pending-payment:{reference}"
    client.setex(key, 86400, json.dumps(data))
    client._test_track(key)  # type: ignore[attr-defined]
    return data


def _post_guest(client, body: dict):
    return client.post("/api/portal/pending-payment/guest", json=body)


def _guest_body(
    plan, reference, *, name=GUEST_NAME, phone=GUEST_PHONE_RAW, email=GUEST_EMAIL
) -> dict:
    return {
        "guest_name": name,
        "guest_phone": phone,
        "guest_email": email,
        "plan_id": str(plan.id),
        "wompi_reference": reference,
    }


def _webhook_body(reference, amount_in_cents, tx_id="tx-guest-1") -> dict:
    return {
        "wompi_reference": reference,
        "wompi_transaction_id": tx_id,
        "amount_in_cents": amount_in_cents,
    }


def _post_webhook(client, body: dict, secret: str = INTEGRITY_SECRET, signature=None):
    raw = json.dumps(body).encode("utf-8")
    computed = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post(
        "/api/portal/webhook-renew",
        headers={
            "X-Signature": signature if signature is not None else computed,
            "Content-Type": "application/json",
        },
        content=raw,
    )


def _count_rows(db_session, model, **filters):
    return db_session.query(model).filter_by(**filters).count()


def _member_by_phone(db_session, phone: str):
    return (
        db_session.query(Member)
        .filter(Member.phone == phone)
        .order_by(Member.created_at.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# Phase 3 — canonical phone service (tasks 3.1 / 3.2)
# ---------------------------------------------------------------------------


class TestCanonicalizePhone:
    """Task 3.1: extraction of portal_auth._canonicalize_phone, unchanged."""

    def test_ten_digit_mobile_gets_country_code(self):
        from services.canonical_phone import canonicalize_phone

        assert canonicalize_phone("3001112233") == "573001112233"

    def test_formatted_number_normalizes_to_same_canonical_form(self):
        from services.canonical_phone import canonicalize_phone

        assert canonicalize_phone("+57 (300) 111 2233") == "573001112233"

    def test_already_canonical_number_is_unchanged(self):
        from services.canonical_phone import canonicalize_phone

        assert canonicalize_phone("573001112233") == "573001112233"

    def test_landline_without_country_code_is_unchanged(self):
        """Non-mobile 10-digit numbers keep their digits (legacy parity)."""
        from services.canonical_phone import canonicalize_phone

        assert canonicalize_phone("6015550100") == "6015550100"


class TestResolveMemberByPhone:
    """Task 3.1: resolve_member_by_phone — 0 hits → None, >1 → None
    (ambiguous), exactly 1 → member."""

    def test_no_match_returns_none(self, db_session):
        from services.canonical_phone import resolve_member_by_phone

        assert resolve_member_by_phone(db_session, "573009998877") is None

    def test_single_match_returns_member(self, db_session):
        from services.canonical_phone import resolve_member_by_phone

        member = Member(
            first_name="Ana",
            last_name="Perez",
            email=f"ana-{uuid.uuid4().hex[:8]}@example.com",
            phone="300 111 2233",  # stored in legacy formatted form
            status="active",
        )
        db_session.add(member)
        db_session.flush()

        resolved = resolve_member_by_phone(db_session, GUEST_PHONE)
        assert resolved is not None
        assert str(resolved.id) == str(member.id)

    def test_ambiguous_match_returns_none(self, db_session):
        """Legacy duplicate rows (same canonical phone, different formats)
        must resolve to None — never a coin-flip member."""
        from services.canonical_phone import resolve_member_by_phone

        db_session.add_all(
            [
                Member(
                    first_name="Ana",
                    last_name="Perez",
                    email=f"ana1-{uuid.uuid4().hex[:8]}@example.com",
                    phone="3001112233",
                    status="active",
                ),
                Member(
                    first_name="Ana",
                    last_name="Dupe",
                    email=f"ana2-{uuid.uuid4().hex[:8]}@example.com",
                    phone="+57 300 111 2233",
                    status="active",
                ),
            ]
        )
        db_session.flush()

        assert resolve_member_by_phone(db_session, GUEST_PHONE) is None

    def test_different_phone_does_not_match(self, db_session):
        from services.canonical_phone import resolve_member_by_phone

        member = Member(
            first_name="Otro",
            last_name="Numero",
            email=f"otro-{uuid.uuid4().hex[:8]}@example.com",
            phone="3019998877",
            status="active",
        )
        db_session.add(member)
        db_session.flush()

        assert resolve_member_by_phone(db_session, GUEST_PHONE) is None


class TestPortalAuthReusesService:
    """Task 3.2: portal_auth imports the service — reuse, not a copy."""

    def test_portal_auth_symbols_are_the_service_functions(self):
        from services.canonical_phone import (
            canonicalize_phone,
            resolve_member_by_phone,
        )

        assert portal_auth_module._canonicalize_phone is canonicalize_phone
        assert portal_auth_module._resolve_member is resolve_member_by_phone


# ---------------------------------------------------------------------------
# Phase 4 — guest pending endpoint, design D10 (tasks 4.1 / 4.2)
# ---------------------------------------------------------------------------


class TestGuestPendingEndpoint:
    """POST /api/portal/pending-payment/guest — no JWT, D10 contract."""

    def test_guest_identity_stores_v2_pending_record(
        self, client, portal_redis, gym_plan
    ):
        """Scenario: Guest identity captured for a gym plan [pytest] +
        Pending record carries identity, not a member [pytest]."""
        reference = _guest_reference()
        # No Authorization header anywhere in this class — guests have no
        # token; if the endpoint demanded JWT these would all 401.
        resp = _post_guest(client, _guest_body(gym_plan, reference))

        assert resp.status_code == 200, (resp.status_code, resp.text)
        assert resp.json()["status"] == "stored"

        raw = portal_redis.get(f"pending-payment:{reference}")
        assert raw is not None, "pending record must be stored"
        record = json.loads(raw)

        assert record["v"] == 2
        assert record["guest_name"] == GUEST_NAME
        assert record["guest_phone"] == GUEST_PHONE  # normalized 57+10
        assert record["guest_email"] == GUEST_EMAIL
        assert record["plan_id"] == str(gym_plan.id)
        assert record["wompi_reference"] == reference
        # Identity, not a member — the webhook decides attachment later.
        assert record["member_id"] is None
        # TTL: not exceeding 24h (spec: Pending Guest Record).
        ttl = portal_redis.ttl(f"pending-payment:{reference}")
        assert 0 < ttl <= 86400

    def test_pending_amount_equals_plan_price(self, client, portal_redis, gym_plan):
        """Task 4.1: Pending amount equals plan price — server-authored."""
        reference = _guest_reference()
        body = _guest_body(gym_plan, reference)
        # There is no amount field on the guest schema at all — the record
        # must carry the DB plan price regardless of anything the client
        # could try to send.
        body["amount"] = 1  # ignored even if smuggled in
        resp = _post_guest(client, body)
        assert resp.status_code == 200, (resp.status_code, resp.text)

        record = json.loads(portal_redis.get(f"pending-payment:{reference}"))
        assert Decimal(record["amount"]) == Decimal(str(gym_plan.price))

    def test_phone_normalization_variants(self, client, portal_redis, gym_plan):
        """57+10 variants: formatted, bare mobile, prefixed — one canonical."""
        variants = {
            "300 111 2233": GUEST_PHONE,
            "3001112233": GUEST_PHONE,
            "+57 300 111 2233": GUEST_PHONE,
            "(+57)3001112233": GUEST_PHONE,
            "573001112233": GUEST_PHONE,
        }
        for raw_phone, canonical in variants.items():
            reference = _guest_reference()
            resp = _post_guest(
                client, _guest_body(gym_plan, reference, phone=raw_phone)
            )
            assert resp.status_code == 200, (raw_phone, resp.status_code, resp.text)
            record = json.loads(portal_redis.get(f"pending-payment:{reference}"))
            assert record["guest_phone"] == canonical, raw_phone

    def test_non_canonical_phone_is_rejected(self, client, portal_redis, gym_plan):
        """Scenario: Non-canonical phone is rejected [pytest] — 422 and NO
        pending record stored."""
        bad_phones = [
            "1234",  # too short
            "6011234567",  # 10 digits but landline (no 57)
            "583001112233",  # wrong country code
            "300111223",  # 9 digits
            "30011122334",  # 11 digits starting with 3
            "57300111223",  # 57 + 9 digits
            "hello-world",  # no digits at all
        ]
        for bad in bad_phones:
            reference = _guest_reference()
            resp = _post_guest(client, _guest_body(gym_plan, reference, phone=bad))
            assert resp.status_code == 422, (bad, resp.status_code, resp.text)
            assert portal_redis.get(f"pending-payment:{reference}") is None, bad

    def test_bad_reference_format_is_rejected(self, client, portal_redis, gym_plan):
        """D10: the Wompi reference must match the signature format."""
        bad_references = [
            "guest-123",  # no PH- prefix structure
            "PH-GUEST-ABC-20260818-0a1b2c",  # uppercase
            "PH-guest-x-1755490000-0a1b2",  # 5-hex checksum
            "ph-guest-x-1755490000-0a1b2c",  # lowercase prefix
            "PH--1755490000-0a1b2c",  # empty slug
            "PH-guest-x-1755490000-0A1B2C",  # uppercase hex
            "PH-guest-x-175549000-0a1b2c",  # 9-digit timestamp
        ]
        for bad in bad_references:
            resp = _post_guest(client, _guest_body(gym_plan, bad))
            assert resp.status_code == 422, (bad, resp.status_code, resp.text)
            assert portal_redis.get(f"pending-payment:{bad}") is None

    def test_invalid_name_or_email_is_rejected(self, client, portal_redis, gym_plan):
        reference = _guest_reference()
        bad_bodies = [
            _guest_body(gym_plan, reference, name="   "),
            _guest_body(gym_plan, reference, name="M"),
            _guest_body(gym_plan, reference, email="not-an-email"),
            _guest_body(gym_plan, reference, email=""),
        ]
        for body in bad_bodies:
            resp = _post_guest(client, body)
            assert resp.status_code == 422, (body, resp.status_code, resp.text)
        assert portal_redis.get(f"pending-payment:{reference}") is None

    def test_unknown_or_inactive_plan_is_rejected(
        self, client, portal_redis, db_session
    ):
        reference = _guest_reference()
        inactive = MembershipPlan(
            name="Viejo",
            duration_days=30,
            price=Decimal("30000"),
            is_active=False,
        )
        db_session.add(inactive)
        db_session.flush()

        for plan_id in (str(inactive.id), str(uuid.uuid4())):
            resp = _post_guest(
                client, _guest_body(type("P", (), {"id": plan_id})(), reference)
            )
            assert resp.status_code == 404, (plan_id, resp.status_code, resp.text)
        assert portal_redis.get(f"pending-payment:{reference}") is None

    def test_guest_endpoint_is_rate_limited(
        self, client, portal_redis, gym_plan, monkeypatch
    ):
        """D10: slowapi caps Redis stuffing (pattern of MEMBER_AUTH_RATE_LIMIT)."""
        from core.config import settings as live_settings

        limit = live_settings.GUEST_CHECKOUT_RATE_LIMIT.split("/")[0]
        budget = int(limit)

        # Requests that pass schema validation but fail in the handler
        # (non-canonical phone) still consume quota: handler-executed 422s.
        for i in range(budget):
            resp = _post_guest(
                client,
                _guest_body(
                    gym_plan,
                    _guest_reference(),
                    phone="6011234567",
                ),
            )
            assert resp.status_code == 422, resp.text

        # Budget exhausted → the next VALID request is 429, nothing stored.
        good_reference = _guest_reference()
        blocked = _post_guest(client, _guest_body(gym_plan, good_reference))
        assert blocked.status_code == 429, (blocked.status_code, blocked.text)
        assert portal_redis.get(f"pending-payment:{good_reference}") is None

    def test_no_secret_reaches_guest_endpoint_response(
        self, client, portal_redis, gym_plan, webhook_env
    ):
        reference = _guest_reference()
        responses = [
            _post_guest(client, _guest_body(gym_plan, reference)),
            _post_guest(client, _guest_body(gym_plan, "guest-invalid")),
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


# ---------------------------------------------------------------------------
# Phase 4 — webhook guest provisioning branch (tasks 4.3 / 4.4, design D5/D9)
# ---------------------------------------------------------------------------


class _FakeCvResponse:
    status_code = 200


class _FakeCvClient:
    """Captures CV invalidation calls instead of hitting a network."""

    def __init__(self, captured):
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, headers=None):
        self._captured["url"] = url
        self._captured["headers"] = headers
        return _FakeCvResponse()


@pytest.fixture
def real_cv_notify(monkeypatch):
    """Let the REAL notify_cv_invalidation run against a fake httpx client,
    with a test CV_API_KEY — proves the X-API-Key contract end-to-end.

    Sets the integrity secret (like webhook_env) but deliberately does NOT
    mock the notifier itself."""
    import services.cv_notify as cv_notify_module

    monkeypatch.setattr(app_settings, "WOMPI_INTEGRITY_SECRET", INTEGRITY_SECRET)
    captured: dict = {}
    monkeypatch.setattr(app_settings, "CV_API_KEY", CV_TEST_KEY)

    def factory(*args, **kwargs):
        return _FakeCvClient(captured)

    monkeypatch.setattr(cv_notify_module.httpx, "AsyncClient", factory)
    return captured


class TestGuestProvisioningWebhook:
    """Guest branch of /portal/webhook-renew: pending v2 record without
    member_id provisions Member+Membership+Sale atomically (D5)."""

    def _provision(
        self,
        client,
        db_session,
        gym_plan,
        portal_redis,
        *,
        reference=None,
        phone=GUEST_PHONE,
        name=GUEST_NAME,
        email=GUEST_EMAIL,
    ):
        """Seed a guest pending record and post the signed webhook."""
        reference = reference or _guest_reference()
        _store_guest_pending(
            portal_redis,
            plan=gym_plan,
            reference=reference,
            name=name,
            phone=phone,
            email=email,
        )
        resp = _post_webhook(client, _webhook_body(reference, _cents(gym_plan)))
        return reference, resp

    def test_guest_payment_provisions_all_records(
        self, client, db_session, gym_plan, portal_redis, webhook_env
    ):
        """Scenario: Approved payment provisions all records [pytest] +
        New phone creates a new member [pytest] — via the v2 guest record."""
        before = _count_rows(db_session, Member)
        reference, resp = self._provision(client, db_session, gym_plan, portal_redis)

        assert resp.status_code == 200, (resp.status_code, resp.text)
        assert resp.json()["status"] == "success"

        members = _member_by_phone(db_session, GUEST_PHONE)
        assert len(members) == 1, "exactly one new Member row"
        member = members[0]
        # D5 mapping: first token / remainder; no biometric consent implied.
        assert member.first_name == "Maria"
        assert member.last_name == "Fernanda Lopez"
        assert member.email == GUEST_EMAIL
        assert member.status == "active"
        assert member.consent_given_at is None
        assert member.facial_data_enrolled is False
        assert _count_rows(db_session, Member) == before + 1

        membership = (
            db_session.query(Membership).filter_by(member_id=str(member.id)).one()
        )
        assert membership.status == "active"
        assert membership.plan_id == gym_plan.id
        assert membership.end_date == date.today() + timedelta(
            days=gym_plan.duration_days
        )

        sale = (
            db_session.query(SalesTransaction)
            .filter_by(wompi_reference=reference)
            .one()
        )
        assert Decimal(str(sale.amount)) == Decimal(str(gym_plan.price))
        assert str(sale.membership_id) == str(membership.id)

        # Key consumed strictly after commit.
        assert portal_redis.get(f"pending-payment:{reference}") is None
        webhook_env.assert_awaited_once_with(str(member.id))

    def test_single_token_name_maps_to_empty_last_name(
        self, client, db_session, gym_plan, portal_redis, webhook_env
    ):
        """D5 edge: 'Cher' → first_name='Cher', last_name=''."""
        _, resp = self._provision(
            client, db_session, gym_plan, portal_redis, name="Cher"
        )
        assert resp.status_code == 200, resp.text
        member = _member_by_phone(db_session, GUEST_PHONE)[0]
        assert member.first_name == "Cher"
        assert member.last_name == ""

    def test_existing_phone_attaches_no_duplicate(
        self, client, db_session, gym_plan, portal_redis, webhook_env
    ):
        """Scenario: Existing phone attaches to the existing member [pytest]
        — stored in a legacy format, resolved through canonical SQL."""
        existing = Member(
            first_name="Ya",
            last_name="Existe",
            email=f"ya-{uuid.uuid4().hex[:8]}@example.com",
            phone="300 111 2233",  # legacy formatted — same canonical
            status="active",
        )
        db_session.add(existing)
        db_session.flush()
        before = _count_rows(db_session, Member)

        _, resp = self._provision(client, db_session, gym_plan, portal_redis)

        assert resp.status_code == 200, (resp.status_code, resp.text)
        assert _count_rows(db_session, Member) == before, "no duplicate row"

        sale = (
            db_session.query(SalesTransaction)
            .order_by(SalesTransaction.created_at.desc())
            .first()
        )
        assert str(sale.member_id) == str(existing.id)
        membership = (
            db_session.query(Membership)
            .filter_by(member_id=str(existing.id))
            .order_by(Membership.created_at.desc())
            .first()
        )
        assert membership is not None

    def test_membership_stacks_from_furthest_end_date(
        self, client, db_session, gym_plan, portal_redis, webhook_env
    ):
        """Task 4.4: attach on an active membership → start = end+1."""
        existing = Member(
            first_name="Activa",
            last_name="Hasta",
            email=f"activa-{uuid.uuid4().hex[:8]}@example.com",
            phone="573001112233",
            status="active",
        )
        db_session.add(existing)
        db_session.flush()
        running_end = date.today() + timedelta(days=10)
        db_session.add(
            Membership(
                member_id=str(existing.id),
                plan_id=gym_plan.id,
                type=gym_plan.name,
                start_date=date.today() - timedelta(days=20),
                end_date=running_end,
                price=Decimal("69900"),
                status="active",
            )
        )
        db_session.flush()

        _, resp = self._provision(client, db_session, gym_plan, portal_redis)

        assert resp.status_code == 200, resp.text
        stacked = (
            db_session.query(Membership)
            .filter_by(member_id=str(existing.id))
            .order_by(Membership.start_date.desc())
            .first()
        )
        assert stacked.start_date == running_end + timedelta(days=1)
        assert stacked.end_date == running_end + timedelta(
            days=1 + gym_plan.duration_days
        )

    def test_failure_mid_commit_leaves_no_partial_records(
        self,
        client,
        db_session,
        gym_plan,
        portal_redis,
        webhook_env,
        monkeypatch,
    ):
        """Scenario: Failure mid-commit leaves no partial records [pytest].

        The Member insert happened (flushed) but the final commit fails —
        the whole transaction must roll back: no Member, no Membership,
        no Sale. Key retained."""
        reference = _guest_reference()
        _store_guest_pending(portal_redis, plan=gym_plan, reference=reference)

        def _boom():
            raise RuntimeError("simulated commit failure")

        monkeypatch.setattr(db_session, "commit", _boom)
        with pytest.raises(RuntimeError):
            _post_webhook(client, _webhook_body(reference, _cents(gym_plan)))

        db_session.rollback()
        assert _member_by_phone(db_session, GUEST_PHONE) == []
        # No orphaned membership for the rolled-back member either.
        assert (
            db_session.query(Membership)
            .filter(
                Membership.member_id.in_(
                    [
                        str(m.id)
                        for m in db_session.query(Member).filter_by(phone=GUEST_PHONE)
                    ]
                )
            )
            .count()
            == 0
        )
        assert (
            db_session.query(SalesTransaction)
            .filter_by(wompi_reference=reference)
            .count()
            == 0
        )
        assert portal_redis.get(f"pending-payment:{reference}") is not None
        webhook_env.assert_not_awaited()

    def test_ambiguous_phone_is_refused_422_no_writes(
        self, client, db_session, gym_plan, portal_redis, webhook_env, caplog
    ):
        """Task 4.3: legacy duplicates (>1 canonical match) → 422 + alert,
        no writes, key retained — never a coin-flip member."""
        db_session.add_all(
            [
                Member(
                    first_name="Dup",
                    last_name="Uno",
                    email=f"dup1-{uuid.uuid4().hex[:8]}@example.com",
                    phone="3001112233",
                    status="active",
                ),
                Member(
                    first_name="Dup",
                    last_name="Dos",
                    email=f"dup2-{uuid.uuid4().hex[:8]}@example.com",
                    phone="+57 300 111 2233",
                    status="active",
                ),
            ]
        )
        db_session.flush()
        before = _count_rows(db_session, Member)

        reference = _guest_reference()
        with caplog.at_level(logging.ERROR, logger="api.portal"):
            _store_guest_pending(portal_redis, plan=gym_plan, reference=reference)
            resp = _post_webhook(client, _webhook_body(reference, _cents(gym_plan)))

        assert resp.status_code == 422, (resp.status_code, resp.text)
        assert GUEST_PHONE in caplog.text

        assert _count_rows(db_session, Member) == before
        assert (
            db_session.query(SalesTransaction)
            .filter_by(wompi_reference=reference)
            .count()
            == 0
        )
        assert portal_redis.get(f"pending-payment:{reference}") is not None
        webhook_env.assert_not_awaited()

    def test_email_collision_retries_null_and_logs(
        self, client, db_session, gym_plan, portal_redis, webhook_env, caplog
    ):
        """Task 4.3/D5: guest email already owned by another member → the
        new member is stored with email NULL + a warning, sale intact."""
        db_session.add(
            Member(
                first_name="Dueno",
                last_name="DelCorreo",
                email=GUEST_EMAIL,  # collides with the guest's email
                phone="573005554443",
                status="active",
            )
        )
        db_session.flush()

        with caplog.at_level(logging.WARNING, logger="api.portal"):
            reference, resp = self._provision(
                client, db_session, gym_plan, portal_redis
            )

        assert resp.status_code == 200, (resp.status_code, resp.text)
        member = _member_by_phone(db_session, GUEST_PHONE)[0]
        assert member.email is None
        assert GUEST_EMAIL in caplog.text

        sale = (
            db_session.query(SalesTransaction)
            .filter_by(wompi_reference=reference)
            .one()
        )
        assert sale is not None

    def test_provisioning_lock_serializes_same_phone(
        self, client, db_session, gym_plan, portal_redis, webhook_env, caplog
    ):
        """Task 4.4: Redis advisory lock member-provision:{phone} NX EX 15.

        Harness limit: TestClient cannot run two webhooks in parallel, so
        this proves the CONTRACT, not a true race — a held lock means a
        concurrent provisioning is in flight: 409, zero writes, key
        retained; once released, the replay succeeds."""
        lock_key = f"member-provision:{GUEST_PHONE}"
        portal_redis.setex(lock_key, 15, "1")
        portal_redis._test_track(lock_key)  # type: ignore[attr-defined]

        reference = _guest_reference()
        _store_guest_pending(portal_redis, plan=gym_plan, reference=reference)
        with caplog.at_level(logging.WARNING, logger="api.portal"):
            resp = _post_webhook(client, _webhook_body(reference, _cents(gym_plan)))

        assert resp.status_code == 409, (resp.status_code, resp.text)
        assert GUEST_PHONE in caplog.text
        assert _member_by_phone(db_session, GUEST_PHONE) == []
        assert portal_redis.get(f"pending-payment:{reference}") is not None
        webhook_env.assert_not_awaited()

        # Lock released → the same webhook replays to success.
        portal_redis.delete(lock_key)
        replay = _post_webhook(client, _webhook_body(reference, _cents(gym_plan)))
        assert replay.status_code == 200, (replay.status_code, replay.text)
        assert len(_member_by_phone(db_session, GUEST_PHONE)) == 1

    def test_guest_replay_reference_is_idempotent(
        self, client, db_session, gym_plan, portal_redis, webhook_env
    ):
        """Scenario: Replayed reference provisions nothing new [pytest] —
        guest variant: exactly one member/membership/sale survives a
        replay of the same webhook."""
        reference, first = self._provision(client, db_session, gym_plan, portal_redis)
        assert first.status_code == 200

        # Simulate the race window (winner's key not yet visible as gone):
        # replay directly against the DB idempotency net.
        replay = _post_webhook(client, _webhook_body(reference, _cents(gym_plan)))
        assert replay.status_code == 200, (replay.status_code, replay.text)
        assert replay.json()["status"] == "already_processed"

        assert len(_member_by_phone(db_session, GUEST_PHONE)) == 1
        assert (
            db_session.query(SalesTransaction)
            .filter_by(wompi_reference=reference)
            .count()
            == 1
        )

    def test_commit_triggers_cv_invalidation_with_api_key(
        self, client, db_session, gym_plan, portal_redis, real_cv_notify
    ):
        """Scenario: Commit triggers CV invalidation with API key [pytest]
        — the REAL notifier runs; the header must carry the CV API key."""
        reference, resp = self._provision(client, db_session, gym_plan, portal_redis)
        assert resp.status_code == 200, resp.text
        member = _member_by_phone(db_session, GUEST_PHONE)[0]

        assert real_cv_notify["headers"]["X-API-Key"] == CV_TEST_KEY
        assert real_cv_notify["url"].endswith(f"/invalidate/{member.id}")

    def test_cv_unreachable_leaves_the_sale_intact(
        self, client, db_session, gym_plan, portal_redis, monkeypatch, caplog
    ):
        """Scenario: CV unreachable leaves the sale intact [pytest]."""
        monkeypatch.setattr(app_settings, "WOMPI_INTEGRITY_SECRET", INTEGRITY_SECRET)
        failing_notify = AsyncMock(side_effect=ConnectionError("cv down"))
        monkeypatch.setattr(portal_module, "notify_cv_invalidation", failing_notify)

        with caplog.at_level(logging.ERROR, logger="api.portal"):
            reference, resp = self._provision(
                client, db_session, gym_plan, portal_redis
            )

        assert resp.status_code == 200, (resp.status_code, resp.text)
        # Rows remain committed; failure logged for retry.
        assert len(_member_by_phone(db_session, GUEST_PHONE)) == 1
        assert (
            db_session.query(SalesTransaction)
            .filter_by(wompi_reference=reference)
            .count()
            == 1
        )
        assert "CV invalidation failed" in caplog.text

    def test_honest_confirmation_data_available(
        self,
        client,
        db_session,
        gym_plan,
        portal_redis,
        webhook_env,
        monkeypatch,
    ):
        """Guest confirmation honesty (backend half): after provisioning,
        the pending record is consumed (no stale 'pending' state) and the
        committed sale carries the reference — everything an honest
        confirmation page needs, and nothing that could claim enrollment."""
        monkeypatch.setattr(app_settings, "PORTAL_INTERNAL_API_KEY", INTERNAL_KEY)
        reference, resp = self._provision(client, db_session, gym_plan, portal_redis)
        assert resp.status_code == 200, resp.text

        pending = client.get(
            f"/api/portal/pending-payment/{reference}",
            headers={"X-API-Key": INTERNAL_KEY},
        )
        assert pending.status_code == 200
        assert pending.json()["status"] == "not_found"

        sale = (
            db_session.query(SalesTransaction)
            .filter_by(wompi_reference=reference)
            .one()
        )
        member = _member_by_phone(db_session, GUEST_PHONE)[0]
        assert str(sale.member_id) == str(member.id)
        # The fresh member carries no biometric claim the UI could lean on.
        assert member.facial_data_enrolled is False
        assert member.consent_given_at is None

    def test_member_id_pending_with_missing_member_still_404(
        self, client, db_session, gym_plan, portal_redis, webhook_env
    ):
        """Guard: the guest branch triggers ONLY when member_id is absent —
        a member-bound record whose member was deleted stays a 404."""
        reference = _guest_reference()
        data = _store_guest_pending(portal_redis, plan=gym_plan, reference=reference)
        data["member_id"] = str(uuid.uuid4())  # nonexistent member
        portal_redis.setex(f"pending-payment:{reference}", 86400, json.dumps(data))

        resp = _post_webhook(client, _webhook_body(reference, _cents(gym_plan)))
        assert resp.status_code == 404, (resp.status_code, resp.text)
        assert (
            db_session.query(SalesTransaction)
            .filter_by(wompi_reference=reference)
            .count()
            == 0
        )

    def test_no_secret_reaches_guest_webhook_response(
        self, client, db_session, gym_plan, portal_redis, webhook_env
    ):
        reference, resp = self._provision(client, db_session, gym_plan, portal_redis)
        assert resp.status_code == 200
        forged = _post_webhook(
            client,
            _webhook_body(_guest_reference(), _cents(gym_plan)),
            signature="deadbeef",
        )
        secrets = (
            INTEGRITY_SECRET,
            INTERNAL_KEY,
            app_settings.SECRET_KEY,
            app_settings.ENCRYPTION_KEY,
            CV_TEST_KEY,
        )
        for response in (resp, forged):
            for secret in secrets:
                assert secret not in response.text

    def test_guest_endpoint_to_webhook_end_to_end(
        self, client, db_session, gym_plan, portal_redis, webhook_env
    ):
        """Full flow: POST guest endpoint (no JWT) → signed webhook → all
        three records committed — the exact production sequence."""
        reference = _guest_reference()
        stored = _post_guest(
            client,
            _guest_body(gym_plan, reference, phone="+57 (300) 111 2233"),
        )
        assert stored.status_code == 200, stored.text

        resp = _post_webhook(client, _webhook_body(reference, _cents(gym_plan)))
        assert resp.status_code == 200, (resp.status_code, resp.text)

        member = _member_by_phone(db_session, GUEST_PHONE)[0]
        assert member.email == GUEST_EMAIL
        assert (
            db_session.query(SalesTransaction)
            .filter_by(wompi_reference=reference)
            .count()
            == 1
        )
        assert portal_redis.get(f"pending-payment:{reference}") is None
        webhook_env.assert_awaited_once_with(str(member.id))
