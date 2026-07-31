"""
Tests for the member portal write boundary + 3-path invalidation contract.

member_portal RLS role is SELECT-only (001_rls_setup.sql:147-151); writes
(`portal_renew`, `portal_webhook_renew`) MUST use the privileged `get_db`
session, never `get_portal_session`. Every renewal path must notify the CV
service post-commit only — never on a failed/rolled-back write.
"""

import hashlib
import hmac
import inspect
import json
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

import redis as redis_lib
import api.portal as portal_module
from api.deps import get_db, get_portal_session
from core.config import settings as app_settings
from core.security import create_access_token
from models.membership import MembershipPlan, Membership
from models.sale import SalesTransaction

portal_redis = redis_lib.from_url(app_settings.REDIS_URL, decode_responses=True)

PIN_STATE_KEYS = (
    "member-pin",
    "member-pin-cooldown",
    "member-failed",
    "member-lockout",
)


@pytest.fixture
def member_token(sample_member):
    return create_access_token(data={"sub": str(sample_member.id), "type": "member"})


@pytest.fixture
def member_auth_headers(member_token):
    return {"Authorization": f"Bearer {member_token}"}


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


def _renew_payload(plan_id):
    return {
        "plan_id": str(plan_id),
        "wompi_reference": f"ref-{uuid.uuid4().hex[:8]}",
        "amount": "50000",
    }


class TestPortalRenewWriteBoundary:
    def test_portal_renew_dependency_is_privileged_get_db_not_portal_session(self):
        """Structural proof of the write-boundary swap (design.md's
        'Portal Write Boundary (corrected)' section)."""
        sig = inspect.signature(portal_module.portal_renew)
        db_param = sig.parameters["db"]
        assert db_param.default.dependency is get_db
        assert db_param.default.dependency is not get_portal_session

    def test_portal_renew_refuses_activation_without_verified_payment(
        self, client, member_auth_headers, sample_plan, db_session, sample_member
    ):
        """portal_renew must NOT create a membership without a verified Wompi
        payment — this is the free-membership exploit (CWE-602/840). With no
        prior webhook, it returns 402 and persists nothing."""
        before_m = (
            db_session.query(Membership)
            .filter_by(member_id=str(sample_member.id))
            .count()
        )
        before_t = (
            db_session.query(SalesTransaction)
            .filter_by(member_id=str(sample_member.id))
            .count()
        )

        resp = client.post(
            "/api/portal/renew",
            headers=member_auth_headers,
            json=_renew_payload(sample_plan.id),
        )
        assert resp.status_code == 402, (resp.status_code, resp.text)

        after_m = (
            db_session.query(Membership)
            .filter_by(member_id=str(sample_member.id))
            .count()
        )
        after_t = (
            db_session.query(SalesTransaction)
            .filter_by(member_id=str(sample_member.id))
            .count()
        )
        assert after_m == before_m  # no membership created
        assert after_t == before_t  # no transaction created


class TestPortalRenewInvalidation:
    def test_portal_renew_confirms_only_after_verified_webhook(
        self, client, member_auth_headers, sample_member, sample_plan, monkeypatch
    ):
        """Activation happens ONLY in the HMAC-verified webhook; portal_renew
        then confirms/returns the membership. Also proves the price is the
        plan's server-side price (50000), not the webhook body amount (1)."""
        from core.config import settings

        monkeypatch.setattr(portal_module, "notify_cv_invalidation", AsyncMock())
        monkeypatch.setattr(settings, "WOMPI_INTEGRITY_SECRET", "test-secret")

        reference = f"ref-{uuid.uuid4().hex[:8]}"
        body = {
            "plan_id": str(sample_plan.id),
            "member_id": str(sample_member.id),
            "wompi_reference": reference,
            "wompi_transaction_id": "tx-1",
            "amount": "1",  # wrong amount — must be ignored (plan.price used)
        }
        raw = json.dumps(body).encode("utf-8")
        signature = hmac.new(b"test-secret", raw, hashlib.sha256).hexdigest()

        # 1. Verified webhook activates the membership.
        resp = client.post(
            "/api/portal/webhook-renew",
            headers={"X-Signature": signature, "Content-Type": "application/json"},
            content=raw,
        )
        assert resp.status_code == 200, (resp.status_code, resp.text)

        # 2. portal_renew now confirms and returns that membership.
        resp2 = client.post(
            "/api/portal/renew",
            headers=member_auth_headers,
            json={
                "plan_id": str(sample_plan.id),
                "wompi_reference": reference,
                "amount": "1",
            },
        )
        assert resp2.status_code == 200, (resp2.status_code, resp2.text)
        data = resp2.json()
        assert data["membership"]["status"] == "active"
        assert data["membership"]["price"] == 50000.0  # plan.price, not body "1"

    def test_portal_renew_missing_plan_does_not_invalidate(
        self, client, member_auth_headers, monkeypatch
    ):
        mock_notify = AsyncMock()
        monkeypatch.setattr(portal_module, "notify_cv_invalidation", mock_notify)

        resp = client.post(
            "/api/portal/renew",
            headers=member_auth_headers,
            json=_renew_payload(uuid.uuid4()),
        )
        assert resp.status_code == 404
        mock_notify.assert_not_awaited()


class TestPortalWebhookRenewInvalidation:
    def _signed_request(self, body: dict, secret: str = "test-secret"):
        raw = json.dumps(body).encode("utf-8")
        signature = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        return raw, signature

    def test_webhook_renew_triggers_post_commit_invalidation(
        self, client, sample_member, sample_plan, monkeypatch
    ):
        from core.config import settings

        mock_notify = AsyncMock()
        monkeypatch.setattr(portal_module, "notify_cv_invalidation", mock_notify)
        monkeypatch.setattr(settings, "WOMPI_INTEGRITY_SECRET", "test-secret")

        body = {
            "plan_id": str(sample_plan.id),
            "member_id": str(sample_member.id),
            "wompi_reference": f"ref-{uuid.uuid4().hex[:8]}",
            "wompi_transaction_id": "tx-1",
            "amount": "50000",
        }
        raw, signature = self._signed_request(body)

        resp = client.post(
            "/api/portal/webhook-renew",
            headers={"X-Signature": signature, "Content-Type": "application/json"},
            content=raw,
        )
        assert resp.status_code == 200
        mock_notify.assert_awaited_once_with(str(sample_member.id))

    def test_webhook_renew_invalid_signature_does_not_invalidate(
        self, client, monkeypatch
    ):
        mock_notify = AsyncMock()
        monkeypatch.setattr(portal_module, "notify_cv_invalidation", mock_notify)

        resp = client.post(
            "/api/portal/webhook-renew",
            headers={"X-Signature": "bad-signature"},
            content=b"{}",
        )
        assert resp.status_code == 401
        mock_notify.assert_not_awaited()


def _fresh_phone():
    """Return a unique 10-digit Colombian-style phone number."""
    return "3" + str(uuid.uuid4().int)[:9]


@pytest.fixture
def pin_phone():
    """Fresh phone with no leftover member-PIN Redis state (cleaned at start
    AND end so tests never leak cooldown/lockout state into each other)."""
    phone = _fresh_phone()
    for suffix in PIN_STATE_KEYS:
        portal_redis.delete(f"{suffix}:{phone}")
    yield phone
    for suffix in PIN_STATE_KEYS:
        portal_redis.delete(f"{suffix}:{phone}")


class TestMemberPinLoginHardening:
    """WS-9 (CWE-203/307): the member PIN login flow must not enumerate
    registered phones and must throttle PIN requests."""

    def test_member_login_unknown_phone_returns_generic_200(self, client, pin_phone):
        """Unknown phone gets the SAME 200 body as a known phone (no 404)."""
        resp = client.post("/api/auth/member-login", json={"phone": pin_phone})
        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "message": "PIN enviado a tu WhatsApp",
            "expires_in": 300,
        }

    def test_member_login_second_call_within_cooldown_429(self, client, pin_phone):
        """member-login now enforces the 60s cooldown (was resend-only)."""
        resp1 = client.post("/api/auth/member-login", json={"phone": pin_phone})
        assert resp1.status_code == 200, resp1.text
        resp2 = client.post("/api/auth/member-login", json={"phone": pin_phone})
        assert resp2.status_code == 429, resp2.text
        assert "Espera 60 segundos" in resp2.json()["detail"]

    def test_member_resend_unknown_phone_returns_generic_200(self, client, pin_phone):
        """Resend for an unknown phone also returns the generic 200 body."""
        resp = client.post("/api/auth/member-resend", json={"phone": pin_phone})
        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "message": "PIN enviado a tu WhatsApp",
            "expires_in": 300,
        }

    def test_member_verify_valid_pin_with_no_member_returns_401(
        self, client, pin_phone
    ):
        """A valid PIN that resolves to no member must look exactly like a
        wrong PIN (401, same detail) — not a 404."""
        portal_redis.setex(f"member-pin:{pin_phone}", 300, "123456")
        resp = client.post(
            "/api/auth/member-verify",
            json={"phone": pin_phone, "pin": "123456"},
        )
        assert resp.status_code == 401, resp.text
        assert resp.json()["detail"] == "Código incorrecto o expirado"
