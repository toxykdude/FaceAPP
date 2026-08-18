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
import logging
import re
import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest

import redis as redis_lib
import api.portal as portal_module
import api.portal_auth as portal_auth_module
from api.deps import get_db, get_portal_session
from core.config import settings as app_settings
from core.security import create_access_token
from models.member import Member
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
        # Seed the Redis pending record the webhook consumes (D9 transport).
        pending_key = f"pending-payment:{reference}"
        portal_redis.setex(
            pending_key,
            86400,
            json.dumps(
                {
                    "plan_id": str(sample_plan.id),
                    "member_id": str(sample_member.id),
                    "amount": str(sample_plan.price),
                    "wompi_reference": reference,
                }
            ),
        )
        body = {
            "wompi_reference": reference,
            "wompi_transaction_id": "tx-1",
            "amount_in_cents": int(sample_plan.price * 100),
            "plan_id": str(sample_plan.id),
            "member_id": str(sample_member.id),
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

        reference = f"ref-{uuid.uuid4().hex[:8]}"
        # Seed the Redis pending record the webhook consumes (D9 transport).
        portal_redis.setex(
            f"pending-payment:{reference}",
            86400,
            json.dumps(
                {
                    "plan_id": str(sample_plan.id),
                    "member_id": str(sample_member.id),
                    "amount": str(sample_plan.price),
                    "wompi_reference": reference,
                }
            ),
        )
        body = {
            "wompi_reference": reference,
            "wompi_transaction_id": "tx-1",
            "amount_in_cents": int(sample_plan.price * 100),
            "plan_id": str(sample_plan.id),
            "member_id": str(sample_member.id),
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


def _destination(phone):
    digits = re.sub(r"[^0-9]", "", phone)
    return f"57{digits}" if len(digits) == 10 and digits.startswith("3") else digits


def _phone_variant(phone, variant):
    if variant == "local":
        return phone
    if variant == "prefixed":
        return f"57{phone}"
    if variant == "spaced":
        return f"57 {phone[:3]} {phone[3:6]} {phone[6:]}"
    return f"+57 ({phone[:3]}) {phone[3:6]}-{phone[6:]}"


def _add_member(db_session, phone, status="active"):
    member = Member(
        first_name="Portal",
        last_name="Member",
        email=f"portal-{uuid.uuid4().hex}@example.com",
        phone=phone,
        status=status,
    )
    db_session.add(member)
    db_session.flush()
    return member


@pytest.fixture
def pin_phone():
    """Fresh phone with no leftover member-PIN Redis state (cleaned at start
    AND end so tests never leak cooldown/lockout state into each other)."""
    phone = _fresh_phone()
    for key_phone in (phone, _destination(phone)):
        for suffix in PIN_STATE_KEYS:
            portal_redis.delete(f"{suffix}:{key_phone}")
    yield phone
    for key_phone in (phone, _destination(phone)):
        for suffix in PIN_STATE_KEYS:
            portal_redis.delete(f"{suffix}:{key_phone}")


@pytest.fixture
def pin_member(db_session, pin_phone):
    return _add_member(db_session, pin_phone)


@pytest.fixture
def pin_send(monkeypatch):
    send = AsyncMock()
    monkeypatch.setattr(portal_auth_module, "_send_whatsapp_pin", send)
    return send


class TestMemberPinLoginHardening:
    """WS-9 (CWE-203/307): the member PIN login flow must not enumerate
    registered phones and must throttle PIN requests."""

    GENERIC_RESPONSE = {"message": "PIN enviado a tu WhatsApp", "expires_in": 300}
    GENERIC_ERROR = "Código incorrecto o expirado"

    def test_zero_candidate_is_unresolved(self, client, pin_phone, pin_send):
        resp = client.post("/api/auth/member-login", json={"phone": pin_phone})
        assert resp.status_code == 200, resp.text
        assert resp.json() == self.GENERIC_RESPONSE
        pin_send.assert_not_awaited()
        assert portal_redis.get(f"member-pin:{_destination(pin_phone)}") is None

    @pytest.mark.parametrize("endpoint", ["member-login", "member-resend"])
    def test_exact_duplicate_is_unresolved(
        self, client, db_session, pin_phone, pin_send, endpoint
    ):
        _add_member(db_session, pin_phone)
        _add_member(db_session, pin_phone)
        resp = client.post(f"/api/auth/{endpoint}", json={"phone": pin_phone})
        assert resp.status_code == 200, resp.text
        assert resp.json() == self.GENERIC_RESPONSE
        pin_send.assert_not_awaited()
        assert portal_redis.get(f"member-pin:{_destination(pin_phone)}") is None

    def test_status_and_history_do_not_disambiguate(
        self, client, db_session, sample_plan, pin_phone, pin_send
    ):
        preferred = _add_member(db_session, pin_phone, status="active")
        _add_member(db_session, f"57{pin_phone}", status="inactive")
        db_session.add(
            Membership(
                member_id=preferred.id,
                plan_id=sample_plan.id,
                type="Monthly",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=30),
                price=sample_plan.price,
                status="active",
            )
        )
        db_session.flush()
        resp = client.post("/api/auth/member-login", json={"phone": pin_phone})
        assert resp.status_code == 200
        pin_send.assert_not_awaited()

    @pytest.mark.parametrize(
        ("stored_variant", "login_variant", "verify_variant"),
        [("local", "prefixed", "punctuated"), ("punctuated", "spaced", "local")],
    )
    def test_canonical_unique_login_is_bound_and_single_use(
        self,
        client,
        db_session,
        pin_phone,
        pin_send,
        stored_variant,
        login_variant,
        verify_variant,
    ):
        member = _add_member(db_session, _phone_variant(pin_phone, stored_variant))
        login_phone = _phone_variant(pin_phone, login_variant)
        resp = client.post("/api/auth/member-login", json={"phone": login_phone})
        assert resp.status_code == 200
        destination, pin = pin_send.await_args.args
        assert destination == _destination(pin_phone)
        challenge = json.loads(portal_redis.get(f"member-pin:{destination}"))
        if not hmac.compare_digest(challenge["member_id"], str(member.id)):
            pytest.fail("PIN challenge is not bound to the selected member")

        payload = {"phone": _phone_variant(pin_phone, verify_variant), "pin": pin}
        verified = client.post("/api/auth/member-verify", json=payload)
        assert verified.status_code == 200, verified.text
        repeated = client.post("/api/auth/member-verify", json=payload)
        assert repeated.status_code == 401
        assert repeated.json()["detail"] == self.GENERIC_ERROR

    def test_ambiguity_added_after_request_denies_token(
        self, client, db_session, pin_member, pin_phone, pin_send
    ):
        client.post("/api/auth/member-login", json={"phone": pin_phone})
        pin = pin_send.await_args.args[1]
        _add_member(db_session, f"57{pin_phone}")
        resp = client.post(
            "/api/auth/member-verify",
            json={"phone": pin_phone, "pin": pin},
        )
        assert resp.status_code == 401
        assert "access_token" not in resp.json()

    def test_member_binding_mismatch_denies_token(
        self, client, db_session, pin_member, pin_phone, pin_send
    ):
        client.post("/api/auth/member-login", json={"phone": pin_phone})
        pin = pin_send.await_args.args[1]
        pin_member.phone = _fresh_phone()
        db_session.flush()
        _add_member(db_session, f"57{pin_phone}")
        resp = client.post(
            "/api/auth/member-verify", json={"phone": pin_phone, "pin": pin}
        )
        assert resp.status_code == 401
        assert "access_token" not in resp.json()

    def test_canonical_variants_share_all_redis_state(
        self, client, pin_member, pin_phone, pin_send
    ):
        client.post("/api/auth/member-login", json={"phone": pin_phone})
        destination = _destination(pin_phone)
        assert portal_redis.exists(f"member-pin:{destination}")
        cooldown = client.post(
            "/api/auth/member-resend",
            json={"phone": _phone_variant(pin_phone, "punctuated")},
        )
        assert cooldown.status_code == 429
        for variant in ("local", "prefixed", "spaced"):
            failed = client.post(
                "/api/auth/member-verify",
                json={"phone": _phone_variant(pin_phone, variant), "pin": "000000"},
            )
            assert failed.status_code == 401
        assert portal_redis.exists(f"member-lockout:{destination}")
        locked = client.post(
            "/api/auth/member-verify",
            json={"phone": _phone_variant(pin_phone, "punctuated"), "pin": "000000"},
        )
        assert locked.status_code == 429

    @pytest.mark.parametrize("stored", ["123456", "{", '{"pin":"123456"}'])
    def test_legacy_or_malformed_challenge_fails_closed(
        self, client, pin_member, pin_phone, stored
    ):
        portal_redis.setex(f"member-pin:{_destination(pin_phone)}", 300, stored)
        resp = client.post(
            "/api/auth/member-verify",
            json={"phone": pin_phone, "pin": "123456"},
        )
        assert resp.status_code == 401, resp.text
        assert resp.json()["detail"] == self.GENERIC_ERROR

    def test_delivery_logs_exclude_sensitive_values(
        self, client, pin_member, pin_phone, monkeypatch, caplog
    ):
        http_client = AsyncMock()
        request = http_client.__aenter__.return_value.post
        request.return_value = type("Response", (), {"status_code": 200})()
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: http_client)
        caplog.set_level(logging.INFO, logger=portal_auth_module.__name__)
        client.post("/api/auth/member-login", json={"phone": pin_phone})
        challenge = portal_redis.get(f"member-pin:{_destination(pin_phone)}")
        pin = re.search(r"\b\d{6}\b", request.await_args.kwargs["json"]["text"]).group()
        sensitive = (_destination(pin_phone), str(pin_member.id), pin, challenge)
        if any(value and value in caplog.text for value in sensitive):
            pytest.fail("portal authentication logs contain sensitive data")
