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
from sqlalchemy import text
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


# ---------------------------------------------------------------------------
# Task 4.3 — cross-member isolation under RLS (member_portal, SELECT-only)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def portal_rls_ready():
    """Skip (with the recorded reason) unless tests/portal_rls_bootstrap.py
    provisioned the member_portal role and MEMBER_PORTAL_DATABASE_URL."""
    from core import database as core_database
    from tests.portal_rls_bootstrap import provisioning_error

    if core_database.PortalSessionLocal is None:
        pytest.skip(
            "member_portal RLS role not provisioned: "
            f"{provisioning_error() or 'unknown reason'}"
        )
    return True


@pytest.fixture
def rls_members(engine, portal_rls_ready):
    """Two committed members (A and B), each with an active membership and a
    payment. Committed — NOT on the rollback-isolated db_session — because the
    member_portal RLS session reads through a separate connection that can
    only see committed rows. Everything is deleted on teardown."""
    from sqlalchemy.orm import Session as OrmSession

    db = OrmSession(bind=engine)
    created = {"transactions": [], "memberships": [], "members": [], "plans": []}
    try:
        plan = MembershipPlan(
            name=f"RLS plan {uuid.uuid4().hex[:8]}",
            duration_days=30,
            price=Decimal("50000"),
            is_active=True,
        )
        db.add(plan)
        db.flush()
        created["plans"].append(plan.id)

        out = []
        for first_name in ("Alicia", "Bruno"):
            member = Member(
                first_name=first_name,
                last_name="Rlstest",
                email=f"rls-{uuid.uuid4().hex}@example.com",
                phone=_fresh_phone(),
                status="active",
            )
            db.add(member)
            db.flush()
            created["members"].append(member.id)

            membership = Membership(
                member_id=member.id,
                plan_id=plan.id,
                type=plan.name,
                start_date=date.today(),
                end_date=date.today() + timedelta(days=30),
                price=plan.price,
                status="active",
            )
            db.add(membership)
            db.flush()
            created["memberships"].append(membership.id)

            transaction = SalesTransaction(
                member_id=member.id,
                membership_id=membership.id,
                amount=plan.price,
                payment_method="card",
                invoice_number=f"RLS-{uuid.uuid4().hex[:12].upper()}",
                notes="rls isolation fixture",
            )
            db.add(transaction)
            db.flush()
            created["transactions"].append(transaction.id)

            out.append(
                {
                    "member_id": member.id,
                    "membership_id": membership.id,
                    "transaction_id": transaction.id,
                    "invoice": transaction.invoice_number,
                }
            )
        db.commit()
        yield {"a": out[0], "b": out[1], "plan_id": plan.id}
    finally:
        for tx_id in created["transactions"]:
            db.query(SalesTransaction).filter_by(id=tx_id).delete(
                synchronize_session=False
            )
        for ms_id in created["memberships"]:
            db.query(Membership).filter_by(id=ms_id).delete(synchronize_session=False)
        for m_id in created["members"]:
            db.query(Member).filter_by(id=m_id).delete(synchronize_session=False)
        for p_id in created["plans"]:
            db.query(MembershipPlan).filter_by(id=p_id).delete(
                synchronize_session=False
            )
        db.commit()
        db.close()


def _portal_session_for(member_id):
    """A real member_portal session (RLS-enforced) scoped to member_id —
    exactly what api.deps.get_portal_session yields in production."""
    from core.database import PortalSessionLocal

    db = PortalSessionLocal()
    db.execute(text("SET LOCAL app.member_id = :mid"), {"mid": str(member_id)})
    return db


class TestPortalRlsIsolation:
    """Task 4.3 — the member_portal role is SELECT-only and row-scoped.

    The API-level test locks the spec scenario (cross-member /portal/me
    denied). The DB-level tests are the load-bearing RLS proofs: the route's
    own WHERE clause would hide B's rows even without RLS, so only a raw
    portal-role session demonstrates the database actually enforces the
    boundary (fails if RLS/policies are missing or weakened).
    """

    def test_portal_me_returns_own_rows_only(self, client, rls_members):
        a, b = rls_members["a"], rls_members["b"]
        token = create_access_token(data={"sub": str(a["member_id"]), "type": "member"})

        resp = client.get(
            "/api/portal/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200, (resp.status_code, resp.text)
        data = resp.json()

        # Positive control — A's own rows ARE visible (RLS allows own rows).
        assert data["active_membership"]["id"] == str(a["membership_id"])
        assert [t["id"] for t in data["recent_payments"]] == [str(a["transaction_id"])]

        # Negative — none of B's identifiers may appear anywhere.
        dumped = json.dumps(data)
        for forbidden in (
            str(b["membership_id"]),
            str(b["transaction_id"]),
            b["invoice"],
        ):
            assert forbidden not in dumped

    def test_portal_me_other_member_sees_only_their_rows(self, client, rls_members):
        """Triangulation: symmetric check from B's token."""
        a, b = rls_members["a"], rls_members["b"]
        token = create_access_token(data={"sub": str(b["member_id"]), "type": "member"})

        resp = client.get(
            "/api/portal/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200, (resp.status_code, resp.text)
        data = resp.json()
        assert data["active_membership"]["id"] == str(b["membership_id"])
        assert [t["id"] for t in data["recent_payments"]] == [str(b["transaction_id"])]
        assert str(a["membership_id"]) not in json.dumps(data)

    def test_portal_role_unfiltered_scan_sees_only_self(self, rls_members):
        """The load-bearing RLS check: with NO query-level WHERE, the database
        itself must filter members to the session's app.member_id."""
        a, b = rls_members["a"], rls_members["b"]
        db = _portal_session_for(a["member_id"])
        try:
            visible = db.query(Member).all()
            assert [str(m.id) for m in visible] == [str(a["member_id"])]
        finally:
            db.rollback()
            db.close()

    def test_portal_role_cannot_read_other_members_membership(self, rls_members):
        """A targeted read of B's membership under A's session returns
        nothing — even when the attacker explicitly asks for B's row."""
        a, b = rls_members["a"], rls_members["b"]
        db = _portal_session_for(a["member_id"])
        try:
            rows = (
                db.query(Membership).filter(Membership.id == b["membership_id"]).all()
            )
            assert rows == []  # empty by setup+RLS (companion test is non-empty)
        finally:
            db.rollback()
            db.close()

    def test_portal_role_without_member_context_sees_nothing(self, rls_members):
        """No app.member_id set → policies compare against NULL → zero rows
        (a portal session that skips the SET LOCAL leaks nothing)."""
        from core.database import PortalSessionLocal

        db = PortalSessionLocal()
        try:
            assert db.query(Member).count() == 0
        finally:
            db.rollback()
            db.close()

    def test_portal_role_cannot_insert(self, rls_members):
        """member_portal is SELECT-only at the GRANT level: writes are denied
        regardless of any policy (runtime complement to the structural
        write-boundary test in test_portal.py)."""
        from sqlalchemy.exc import ProgrammingError

        a = rls_members["a"]
        db = _portal_session_for(a["member_id"])
        try:
            db.add(
                Membership(
                    member_id=a["member_id"],
                    plan_id=rls_members["plan_id"],
                    type="forged",
                    start_date=date.today(),
                    end_date=date.today() + timedelta(days=30),
                    price=Decimal("1"),
                    status="active",
                )
            )
            with pytest.raises(ProgrammingError, match="permission denied"):
                db.flush()
        finally:
            db.rollback()
            db.close()
