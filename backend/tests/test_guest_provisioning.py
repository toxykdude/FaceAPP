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
    return f"ph-guest-{uuid.uuid4().hex[:6]}-{date.today().strftime('%Y%m%d')}-0a1b2c"


def _valid_reference_or(pattern_target: str) -> str:
    return pattern_target


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
