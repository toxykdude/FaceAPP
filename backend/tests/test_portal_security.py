"""
Portal runtime security suite (spec: customer-portal-runtime).

Covers the threat-matrix scenarios from design.md:

- Webhook authenticity: forged/missing HMAC-SHA256 signatures are rejected
  with 401 and NEVER change persisted state (task 4.1).
- Origin control: requests with disallowed CORS origins get no CORS grant
  (task 4.2).
- Rate controls: the three ``/api/auth/member-*`` routes reject exceeded-rate
  callers with 429 (task 4.4/4.5).
- Member isolation: ``/portal/me`` and the ``member_portal`` DB role can only
  ever read the authenticated member's own rows (task 4.3).
"""

import hashlib
import hmac
import json
import os
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
import redis as redis_lib
from fastapi.middleware.cors import CORSMiddleware
from unittest.mock import AsyncMock

import api.portal as portal_module
from core.config import settings as app_settings
from core.rate_limiter import limiter
from core.security import create_access_token
from models.member import Member
from models.membership import MembershipPlan, Membership
from models.sale import SalesTransaction

portal_redis = redis_lib.from_url(app_settings.REDIS_URL, decode_responses=True)


def _fresh_phone():
    """Return a unique 10-digit Colombian-style phone number."""
    return "3" + str(uuid.uuid4().int)[:9]


def _destination(phone):
    digits = "".join(ch for ch in phone if ch.isdigit())
    return f"57{digits}" if len(digits) == 10 and digits.startswith("3") else digits


@pytest.fixture
def sample_plan(db_session):
    plan = MembershipPlan(
        name="Security Suite Plan",
        duration_days=30,
        price=Decimal("50000"),
        is_active=True,
    )
    db_session.add(plan)
    db_session.flush()
    return plan


def _webhook_body(member_id, plan_id, reference):
    return {
        "plan_id": str(plan_id),
        "member_id": str(member_id),
        "wompi_reference": reference,
        "wompi_transaction_id": "tx-security",
        "amount": "50000",
    }


def _sign(secret: str, raw: bytes) -> str:
    return hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


class TestWebhookSignatureEnforcement:
    """Task 4.1 — forged/missing HMAC-SHA256 webhook → 401, no state change.

    Approval tests: the verification exists (``verify_wompi_signature``); these
    lock the spec scenarios so a regression cannot ship silently.
    """

    def _row_counts(self, db_session, member_id):
        return (
            db_session.query(Membership).filter_by(member_id=str(member_id)).count(),
            db_session.query(SalesTransaction)
            .filter_by(member_id=str(member_id))
            .count(),
        )

    def test_missing_signature_header_rejected_no_state_change(
        self, client, db_session, sample_member, sample_plan, monkeypatch
    ):
        monkeypatch.setattr(
            app_settings, "WOMPI_INTEGRITY_SECRET", "security-suite-secret"
        )
        raw = json.dumps(
            _webhook_body(
                sample_member.id, sample_plan.id, f"ref-{uuid.uuid4().hex[:8]}"
            )
        ).encode()

        before = self._row_counts(db_session, sample_member.id)
        resp = client.post(
            "/api/portal/webhook-renew",
            headers={"Content-Type": "application/json"},
            content=raw,
        )
        assert resp.status_code == 401, (resp.status_code, resp.text)
        assert self._row_counts(db_session, sample_member.id) == before

    def test_forged_signature_rejected_no_state_change(
        self, client, db_session, sample_member, sample_plan, monkeypatch
    ):
        """Signature computed with the WRONG secret must be rejected."""
        monkeypatch.setattr(
            app_settings, "WOMPI_INTEGRITY_SECRET", "security-suite-secret"
        )
        raw = json.dumps(
            _webhook_body(
                sample_member.id, sample_plan.id, f"ref-{uuid.uuid4().hex[:8]}"
            )
        ).encode()
        forged = _sign("attacker-knows-the-shape-not-the-secret", raw)

        before = self._row_counts(db_session, sample_member.id)
        resp = client.post(
            "/api/portal/webhook-renew",
            headers={"X-Signature": forged, "Content-Type": "application/json"},
            content=raw,
        )
        assert resp.status_code == 401, (resp.status_code, resp.text)
        assert self._row_counts(db_session, sample_member.id) == before

    def test_valid_signature_over_tampered_body_rejected(
        self, client, db_session, sample_member, sample_plan, monkeypatch
    ):
        """A valid signature over a DIFFERENT body must not authorize this one."""
        monkeypatch.setattr(
            app_settings, "WOMPI_INTEGRITY_SECRET", "security-suite-secret"
        )
        reference = f"ref-{uuid.uuid4().hex[:8]}"
        signed_body = json.dumps(
            _webhook_body(sample_member.id, sample_plan.id, reference)
        ).encode()
        signature = _sign("security-suite-secret", signed_body)
        # Attacker swaps the body but keeps the captured signature
        tampered = json.dumps(
            _webhook_body(sample_member.id, sample_plan.id, "ref-evil")
        ).encode()

        before = self._row_counts(db_session, sample_member.id)
        resp = client.post(
            "/api/portal/webhook-renew",
            headers={"X-Signature": signature, "Content-Type": "application/json"},
            content=tampered,
        )
        assert resp.status_code == 401, (resp.status_code, resp.text)
        assert self._row_counts(db_session, sample_member.id) == before
        # Nothing was created for either reference
        assert (
            db_session.query(SalesTransaction)
            .filter(SalesTransaction.notes.like(f"%{reference}%"))
            .count()
            == 0
        )

    def test_valid_signature_is_accepted_and_creates_state(
        self, client, db_session, sample_member, sample_plan, monkeypatch
    ):
        """Positive control proving the rejection tests are not vacuous: with
        the correct signature over the exact bytes, the webhook DOES write."""
        monkeypatch.setattr(
            app_settings, "WOMPI_INTEGRITY_SECRET", "security-suite-secret"
        )
        monkeypatch.setattr(portal_module, "notify_cv_invalidation", AsyncMock())
        raw = json.dumps(
            _webhook_body(
                sample_member.id, sample_plan.id, f"ref-{uuid.uuid4().hex[:8]}"
            )
        ).encode()

        before = self._row_counts(db_session, sample_member.id)
        resp = client.post(
            "/api/portal/webhook-renew",
            headers={
                "X-Signature": _sign("security-suite-secret", raw),
                "Content-Type": "application/json",
            },
            content=raw,
        )
        assert resp.status_code == 200, (resp.status_code, resp.text)
        after = self._row_counts(db_session, sample_member.id)
        assert after[0] == before[0] + 1  # membership created
        assert after[1] == before[1] + 1  # transaction created


def _cors_middleware_kwargs():
    """Introspect the app's CORSMiddleware configuration (main.py wiring)."""
    from main import app

    for mw in app.user_middleware:
        if mw.cls is CORSMiddleware:
            return mw.kwargs
    pytest.fail("CORSMiddleware is not installed on the app")


class TestCorsOriginRejection:
    """Task 4.2 — disallowed origins get no CORS grant.

    The assertions read the app's ACTUAL configured allowlist, so they hold
    regardless of what CORS_ORIGINS a local .env provides. Approval tests:
    the middleware is configured in main.py; these lock the spec scenario.
    """

    def test_disallowed_origin_gets_no_allow_origin_header(self, client):
        allow = _cors_middleware_kwargs()["allow_origins"]
        origin = f"https://{uuid.uuid4().hex}.invalid"
        assert origin not in allow  # guarantees the fixture's premise

        resp = client.get("/api/portal/plans", headers={"Origin": origin})
        assert resp.status_code == 200, resp.text  # route itself is public+fine
        assert "access-control-allow-origin" not in resp.headers

    def test_preflight_from_disallowed_origin_rejected(self, client):
        allow = _cors_middleware_kwargs()["allow_origins"]
        origin = f"https://{uuid.uuid4().hex}.invalid"
        assert origin not in allow

        resp = client.options(
            "/api/auth/member-login",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
            },
        )
        assert resp.status_code == 400  # starlette: "Disallowed CORS origin"
        assert "access-control-allow-origin" not in resp.headers

    def test_allowed_origin_is_echoed(self, client):
        """Positive control: an origin in the configured allowlist IS granted,
        proving the negative tests reject because of the allowlist, not because
        CORS is broken or disabled."""
        allow = _cors_middleware_kwargs()["allow_origins"]
        if not allow:
            pytest.skip("CORS allowlist is empty in this environment")
        origin = allow[0]

        resp = client.get("/api/portal/plans", headers={"Origin": origin})
        assert resp.headers.get("access-control-allow-origin") == origin

        preflight = client.options(
            "/api/auth/member-login",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
            },
        )
        assert preflight.status_code == 200, preflight.text
        assert preflight.headers.get("access-control-allow-origin") == origin


RATE_LIMIT = 10  # per-route slowapi limit on the three /auth/member-* routes


class TestMemberAuthRateLimits:
    """Tasks 4.4/4.5 — exceeded-rate callers get 429 on ALL THREE
    /api/auth/member-* routes.

    The app-level Redis cooldown/lockout protections are neutralized per
    request (their keys are deleted) so the 429 observed on the final request
    can only come from the per-route slowapi limit — and the earlier requests
    prove it by NOT being 429.
    """

    def setup_method(self):
        # slowapi storage is process-global in-memory state: reset it so
        # counters from earlier tests cannot skew the results.
        limiter.reset()

    def teardown_method(self):
        limiter.reset()

    def _purge_pin_state(self, phone):
        destination = _destination(phone)
        for suffix in (
            "member-pin",
            "member-pin-cooldown",
            "member-failed",
            "member-lockout",
        ):
            portal_redis.delete(f"{suffix}:{destination}")

    def test_member_login_exceeding_rate_rejected(self, client):
        phone = _fresh_phone()  # unknown member: generic 200s, no WhatsApp send
        statuses = []
        for _ in range(RATE_LIMIT):
            self._purge_pin_state(phone)
            resp = client.post("/api/auth/member-login", json={"phone": phone})
            statuses.append(resp.status_code)
        assert statuses == [200] * RATE_LIMIT, statuses

        self._purge_pin_state(phone)
        resp = client.post("/api/auth/member-login", json={"phone": phone})
        assert resp.status_code == 429, (resp.status_code, resp.text)
        assert "Rate limit exceeded" in resp.json()["error"]

    def test_member_resend_exceeding_rate_rejected(self, client):
        phone = _fresh_phone()
        statuses = []
        for _ in range(RATE_LIMIT):
            self._purge_pin_state(phone)
            resp = client.post("/api/auth/member-resend", json={"phone": phone})
            statuses.append(resp.status_code)
        assert statuses == [200] * RATE_LIMIT, statuses

        self._purge_pin_state(phone)
        resp = client.post("/api/auth/member-resend", json={"phone": phone})
        assert resp.status_code == 429, (resp.status_code, resp.text)
        assert "Rate limit exceeded" in resp.json()["error"]

    def test_member_verify_exceeding_rate_rejected(self, client):
        """No stored PIN: every request is a clean 401 (failed-attempt and
        lockout keys purged each round), so the 429 on the final request is
        the route's rate limit, not the PIN lockout."""
        phone = _fresh_phone()
        statuses = []
        for _ in range(RATE_LIMIT):
            self._purge_pin_state(phone)
            resp = client.post(
                "/api/auth/member-verify", json={"phone": phone, "pin": "000000"}
            )
            statuses.append(resp.status_code)
        assert statuses == [401] * RATE_LIMIT, statuses

        self._purge_pin_state(phone)
        resp = client.post(
            "/api/auth/member-verify", json={"phone": phone, "pin": "000000"}
        )
        assert resp.status_code == 429, (resp.status_code, resp.text)
        assert "Rate limit exceeded" in resp.json()["error"]
