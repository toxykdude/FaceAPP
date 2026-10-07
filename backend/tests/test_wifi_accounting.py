"""
WiFi captive-portal accounting tests (POST /api/wifi/accounting,
GET /api/wifi/sessions).

Covers the full start→interim→stop lifecycle, duplicate-packet idempotency
(pfSense retransmits when the Accounting-Response is lost), member
resolution failures that must still record, and the staff-only listing.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from models.member import Member
from models.wifi_session import WifiSession

ACCT_URL = "/api/wifi/accounting"
LIST_URL = "/api/wifi/sessions"


@pytest.fixture
def internal_headers(monkeypatch):
    from core.config import settings

    secret = "test-internal-secret-0123456789abcdef"
    monkeypatch.setattr(settings, "INTERNAL_API_SECRET", secret)
    return {"X-Internal-Secret": secret}


def acct_payload(**overrides):
    base = {
        "status": "start",
        "username": "123456789",
        "acct_session_id": uuid4().hex,
        "nas_ip": "10.162.36.1",
        "framed_ip": "10.162.40.55",
        "calling_station_id": "AA:BB:CC:DD:EE:FF",
    }
    base.update(overrides)
    return base


def make_member(db, id_number="123456789"):
    member = Member(
        first_name="Acct",
        last_name="Tester",
        email=f"{uuid4().hex[:8]}@t.co",
        id_number=id_number,
        status="active",
    )
    db.add(member)
    db.flush()
    return member


def rows(db):
    return db.query(WifiSession).all()


# --- Lifecycle ---------------------------------------------------------------


def test_start_creates_open_session_with_member(client, db_session, internal_headers):
    member = make_member(db_session)
    r = client.post(ACCT_URL, json=acct_payload(), headers=internal_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["recorded"] is True
    assert body["member_id"] == str(member.id)

    (row,) = rows(db_session)
    assert row.ended_at is None
    assert row.calling_station_id == "AA:BB:CC:DD:EE:FF"
    assert row.username == "123456789"


def test_interim_updates_counters_monotonically(client, db_session, internal_headers):
    make_member(db_session)
    session_id = uuid4().hex
    client.post(
        ACCT_URL,
        json=acct_payload(acct_session_id=session_id),
        headers=internal_headers,
    )
    r = client.post(
        ACCT_URL,
        json=acct_payload(
            status="interim",
            acct_session_id=session_id,
            acct_input_octets=1_000_000,
            acct_output_octets=2_000_000,
            acct_session_time=600,
        ),
        headers=internal_headers,
    )
    assert r.status_code == 200
    (row,) = rows(db_session)
    assert row.acct_input_octets == 1_000_000
    assert row.acct_output_octets == 2_000_000
    assert row.acct_session_time == 600

    # A late-retransmitted interim with older counters must not shrink them.
    client.post(
        ACCT_URL,
        json=acct_payload(
            status="interim",
            acct_session_id=session_id,
            acct_input_octets=500_000,
            acct_output_octets=1_000_000,
        ),
        headers=internal_headers,
    )
    (row,) = rows(db_session)
    assert row.acct_input_octets == 1_000_000
    assert row.acct_output_octets == 2_000_000


def test_stop_closes_session_once(client, db_session, internal_headers):
    make_member(db_session)
    session_id = uuid4().hex
    client.post(
        ACCT_URL,
        json=acct_payload(acct_session_id=session_id),
        headers=internal_headers,
    )
    r = client.post(
        ACCT_URL,
        json=acct_payload(
            status="stop",
            acct_session_id=session_id,
            acct_terminate_cause="User-Request",
            acct_session_time=3600,
        ),
        headers=internal_headers,
    )
    assert r.status_code == 200
    (row,) = rows(db_session)
    assert row.ended_at is not None
    assert row.terminate_cause == "User-Request"

    # Retransmitted stop is a no-op.
    client.post(
        ACCT_URL,
        json=acct_payload(
            status="stop",
            acct_session_id=session_id,
            acct_terminate_cause="User-Request",
        ),
        headers=internal_headers,
    )
    (row2,) = rows(db_session)
    assert row2.ended_at == row.ended_at


def test_duplicate_start_is_idempotent(client, db_session, internal_headers):
    make_member(db_session)
    session_id = uuid4().hex
    for _ in range(2):
        r = client.post(
            ACCT_URL,
            json=acct_payload(acct_session_id=session_id),
            headers=internal_headers,
        )
        assert r.status_code == 200
    assert len(rows(db_session)) == 1


def test_unknown_username_still_records(client, db_session, internal_headers):
    r = client.post(
        ACCT_URL,
        json=acct_payload(username="000000000"),
        headers=internal_headers,
    )
    assert r.status_code == 200
    assert r.json()["member_id"] is None
    (row,) = rows(db_session)
    assert row.member_id is None
    assert row.username == "000000000"


def test_interim_without_start_creates_row(client, db_session, internal_headers):
    make_member(db_session)
    r = client.post(
        ACCT_URL,
        json=acct_payload(status="interim", acct_input_octets=42),
        headers=internal_headers,
    )
    assert r.status_code == 200
    (row,) = rows(db_session)
    assert row.acct_input_octets == 42
    assert row.ended_at is None


# --- Service auth ------------------------------------------------------------


def test_accounting_requires_internal_secret(client):
    r = client.post(ACCT_URL, json=acct_payload())
    assert r.status_code == 401


# --- Staff-only listing --------------------------------------------------------


def test_sessions_listing_requires_auth(client):
    r = client.get(LIST_URL)
    assert r.status_code == 401


def test_sessions_listing_staff(client, db_session, auth_headers, internal_headers):
    make_member(db_session)
    open_id = uuid4().hex
    closed_id = uuid4().hex
    client.post(
        ACCT_URL, json=acct_payload(acct_session_id=open_id), headers=internal_headers
    )
    client.post(
        ACCT_URL,
        json=acct_payload(acct_session_id=closed_id, status="stop"),
        headers=internal_headers,
    )

    r = client.get(LIST_URL, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2

    r = client.get(LIST_URL, params={"active_only": True}, headers=auth_headers)
    body = r.json()
    assert body["total"] == 1
    assert body["sessions"][0]["acct_session_id"] == open_id
    assert body["sessions"][0]["ended_at"] is None
