"""
WiFi captive-portal authorization tests (POST /api/wifi/authorize).

Covers every denial reason in the kiosk vocabulary, the payment gate
(pending blocks, partial allows), document normalization, the device cap,
timeout bounds, bilingual messages, and the fail-closed service auth.

These tests mirror the kiosk semantics from cv_service's access validator:
the door and the WiFi must answer the same question the same way.
"""

from datetime import date, timedelta

import pytest

from models.member import Member
from models.membership import Membership, MembershipPlan
from models.sale import SalesTransaction
from models.wifi_session import WifiSession

AUTH_URL = "/api/wifi/authorize"


@pytest.fixture
def internal_headers(monkeypatch):
    """Pin a known internal secret independent of .env (fail-closed S1)."""
    from core.config import settings

    secret = "test-internal-secret-0123456789abcdef"
    monkeypatch.setattr(settings, "INTERNAL_API_SECRET", secret)
    return {"X-Internal-Secret": secret}


def make_member(db, id_number="123456789", status="active", name="Wifi"):
    member = Member(
        first_name=name,
        last_name="Tester",
        email=f"{id_number or 'x'}-{__import__('uuid').uuid4().hex[:8]}@t.co",
        id_number=id_number,
        status=status,
    )
    db.add(member)
    db.flush()
    return member


def make_plan(db, price=50000):
    plan = MembershipPlan(
        name=f"Plan {__import__('uuid').uuid4().hex[:6]}",
        duration_days=30,
        price=price,
    )
    db.add(plan)
    db.flush()
    return plan


def make_membership(
    db,
    member,
    plan,
    start=None,
    end=None,
    status="active",
    price=50000,
):
    membership = Membership(
        member_id=member.id,
        plan_id=plan.id,
        type="monthly",
        start_date=start or date.today() - timedelta(days=5),
        end_date=end or date.today() + timedelta(days=25),
        price=price,
        status=status,
    )
    db.add(membership)
    db.flush()
    return membership


def pay(db, membership, amount):
    tx = SalesTransaction(
        member_id=membership.member_id,
        membership_id=membership.id,
        amount=amount,
        payment_method="cash",
        invoice_number=f"INV-{__import__('uuid').uuid4().hex[:10]}",
    )
    db.add(tx)
    db.flush()
    return tx


# --- Auth (fail closed) ------------------------------------------------------


def test_authorize_requires_internal_secret(client):
    r = client.post(AUTH_URL, json={"document": "123"})
    assert r.status_code == 401


def test_authorize_rejects_wrong_secret(client, internal_headers, monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "INTERNAL_API_SECRET", "real-secret-value")
    r = client.post(
        AUTH_URL, json={"document": "123"}, headers={"X-Internal-Secret": "nope"}
    )
    assert r.status_code == 401


def test_authorize_503_when_secret_unconfigured(client, monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "INTERNAL_API_SECRET", "")
    r = client.post(
        AUTH_URL, json={"document": "123"}, headers={"X-Internal-Secret": "x"}
    )
    assert r.status_code == 503


# --- Grant path --------------------------------------------------------------


def test_active_paid_member_allowed(client, db_session, internal_headers):
    member = make_member(db_session, id_number="1010101010")
    plan = make_plan(db_session)
    membership = make_membership(db_session, member, plan)
    pay(db_session, membership, 50000)

    r = client.post(AUTH_URL, json={"document": "1010101010"}, headers=internal_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["allowed"] is True
    assert body["reason"] is None
    assert body["member_id"] == str(member.id)
    assert body["member_name"] == "Wifi Tester"
    assert body["plan_name"] == plan.name
    assert body["membership_end_date"] == membership.end_date.isoformat()
    assert 60 <= body["session_timeout_seconds"] <= 4 * 60 * 60
    assert body["idle_timeout_seconds"] == 1800
    assert body["acct_interim_interval_seconds"] == 600
    assert body["message_es"] and body["message_en"]


def test_partial_payment_allowed(client, db_session, internal_headers):
    member = make_member(db_session, id_number="2020202020")
    membership = make_membership(db_session, member, make_plan(db_session))
    pay(db_session, membership, 20000)

    r = client.post(AUTH_URL, json={"document": "2020202020"}, headers=internal_headers)
    assert r.json()["allowed"] is True


def test_document_normalization_punctuation(client, db_session, internal_headers):
    member = make_member(db_session, id_number="1.234.567")
    membership = make_membership(db_session, member, make_plan(db_session))
    pay(db_session, membership, 50000)

    # Same document with different punctuation/case must resolve identically.
    for doc in ("1234567", "1.234.567", " 1 234 567 ", "1.234.567"):
        r = client.post(AUTH_URL, json={"document": doc}, headers=internal_headers)
        assert r.status_code == 200, doc
        assert r.json()["allowed"] is True, doc


# --- Denial paths ------------------------------------------------------------


def test_unknown_document(client, db_session, internal_headers):
    r = client.post(AUTH_URL, json={"document": "999999999"}, headers=internal_headers)
    body = r.json()
    assert body["allowed"] is False
    assert body["reason"] == "member_not_found"
    assert "recepción" in body["message_es"] or "recep" in body["message_es"].lower()


def test_inactive_member(client, db_session, internal_headers):
    make_member(db_session, id_number="3030303030", status="inactive")
    r = client.post(AUTH_URL, json={"document": "3030303030"}, headers=internal_headers)
    assert r.json()["reason"] == "member_inactive"


def test_no_membership(client, db_session, internal_headers):
    make_member(db_session, id_number="4040404040")
    r = client.post(AUTH_URL, json={"document": "4040404040"}, headers=internal_headers)
    assert r.json()["reason"] == "no_active_membership"


def test_expired_membership(client, db_session, internal_headers):
    member = make_member(db_session, id_number="5050505050")
    make_membership(
        db_session,
        member,
        make_plan(db_session),
        start=date.today() - timedelta(days=40),
        end=date.today() - timedelta(days=10),
    )
    r = client.post(AUTH_URL, json={"document": "5050505050"}, headers=internal_headers)
    assert r.json()["reason"] == "expired_membership"


def test_suspended_membership(client, db_session, internal_headers):
    member = make_member(db_session, id_number="6060606060")
    make_membership(db_session, member, make_plan(db_session), status="suspended")
    r = client.post(AUTH_URL, json={"document": "6060606060"}, headers=internal_headers)
    assert r.json()["reason"] == "suspended_membership"


def test_future_membership(client, db_session, internal_headers):
    member = make_member(db_session, id_number="7070707070")
    make_membership(
        db_session,
        member,
        make_plan(db_session),
        start=date.today() + timedelta(days=5),
        end=date.today() + timedelta(days=35),
    )
    r = client.post(AUTH_URL, json={"document": "7070707070"}, headers=internal_headers)
    assert r.json()["reason"] == "membership_not_started"


def test_unpaid_membership(client, db_session, internal_headers):
    member = make_member(db_session, id_number="8080808080")
    make_membership(db_session, member, make_plan(db_session))  # no payment rows
    r = client.post(AUTH_URL, json={"document": "8080808080"}, headers=internal_headers)
    body = r.json()
    assert body["allowed"] is False
    assert body["reason"] == "unpaid_membership"
    assert "Pendiente de pago" in body["message_es"]


# --- Device cap --------------------------------------------------------------


def _open_session(db, member, age_hours=0):
    from datetime import datetime, timezone

    ws = WifiSession(
        member_id=member.id,
        username=member.id_number or "x",
        nas_ip="10.0.0.1",
        acct_session_id=__import__("uuid").uuid4().hex,
    )
    db.add(ws)
    db.flush()
    return ws


def test_device_limit_blocks_fourth_device(client, db_session, internal_headers):
    member = make_member(db_session, id_number="9090909090")
    membership = make_membership(db_session, member, make_plan(db_session))
    pay(db_session, membership, 50000)
    for _ in range(3):
        _open_session(db_session, member)

    r = client.post(AUTH_URL, json={"document": "9090909090"}, headers=internal_headers)
    assert r.json()["reason"] == "device_limit"


def test_ended_sessions_do_not_count(client, db_session, internal_headers):
    member = make_member(db_session, id_number="9191919191")
    membership = make_membership(db_session, member, make_plan(db_session))
    pay(db_session, membership, 50000)
    from datetime import datetime, timezone

    naive_now = datetime.now(timezone.utc).replace(tzinfo=None)
    for _ in range(3):
        ws = _open_session(db_session, member)
        ws.ended_at = naive_now

    r = client.post(AUTH_URL, json={"document": "9191919191"}, headers=internal_headers)
    assert r.json()["allowed"] is True


def test_stale_sessions_do_not_count(client, db_session, internal_headers):
    member = make_member(db_session, id_number="9292929292")
    membership = make_membership(db_session, member, make_plan(db_session))
    pay(db_session, membership, 50000)
    from datetime import datetime, timezone

    stale = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=48)
    for _ in range(3):
        ws = _open_session(db_session, member)
        ws.last_update_at = stale

    r = client.post(AUTH_URL, json={"document": "9292929292"}, headers=internal_headers)
    assert r.json()["allowed"] is True


# --- Timeout math ------------------------------------------------------------


def test_membership_ending_today_still_grants(client, db_session, internal_headers):
    member = make_member(db_session, id_number="9393939393")
    membership = make_membership(
        db_session,
        member,
        make_plan(db_session),
        end=date.today(),  # inclusive, like the kiosk
    )
    pay(db_session, membership, 50000)

    r = client.post(AUTH_URL, json={"document": "9393939393"}, headers=internal_headers)
    body = r.json()
    assert body["allowed"] is True
    assert body["days_remaining"] == 0
    # Until local midnight — at least the 60s floor.
    assert body["session_timeout_seconds"] >= 60


def test_timeout_capped_for_long_memberships(client, db_session, internal_headers):
    member = make_member(db_session, id_number="9494949494")
    make_membership(
        db_session,
        member,
        make_plan(db_session),
        end=date.today() + timedelta(days=300),
    )
    # note: unpaid → make it paid
    membership = (
        db_session.query(Membership).filter(Membership.member_id == member.id).first()
    )
    pay(db_session, membership, 50000)

    r = client.post(AUTH_URL, json={"document": "9494949494"}, headers=internal_headers)
    assert r.json()["session_timeout_seconds"] == 4 * 60 * 60
