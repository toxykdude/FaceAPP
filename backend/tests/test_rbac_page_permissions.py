"""
RBAC page-permission tests for the WS-3 require_staff -> require_page migration.

Each domain route was previously protected only by require_staff (a role check,
no page granularity), so a staff user denied a page in the UI could still call
that page's API. These tests assert the granular require_page enforcement:
staff WITH the page -> 200; staff WITHOUT the page -> 403; admin -> 200.

Also covers the deny-by-default permissions fix (privilege-management.
default-staff-all-pages, CWE-269): a new user with no explicit permissions
gets {"pages": []}, not {"pages": ["all"]}.
"""

import uuid

import pytest

from core.security import create_access_token, get_password_hash
from models.user import User


def _make_staff(db_session, pages):
    """Create a STAFF user with an explicit pages grant and return it."""
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"staff-{suffix}",
        email=f"staff-{suffix}@example.com",
        password_hash=get_password_hash("secret123"),
        role="staff",
        is_active=True,
        permissions={"pages": pages},
    )
    db_session.add(user)
    db_session.flush()
    return user


def _authed_client(client, user):
    token = create_access_token(data={"sub": str(user.id)})
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


# ---- per-domain RBAC: (route, page required, method, json body) ----

RBAC_CASES = [
    ("/api/memberships", "memberships", "GET", None),
    ("/api/membership-plans", "memberships", "GET", None),
    ("/api/sales", "sales", "GET", None),
    ("/api/members/import", "reports", "POST", None),
    ("/api/reports-email/send-now", "reports", "POST", None),
]


@pytest.mark.parametrize("route,page,method,body", RBAC_CASES)
def test_staff_without_page_gets_403(client, db_session, route, page, method, body):
    """Staff denied the page must be blocked (the bug these routes had)."""
    user = _make_staff(db_session, pages=[])  # no pages at all
    c = _authed_client(client, user)
    resp = c.request(method, route, json=body) if body else c.request(method, route)
    assert resp.status_code == 403, (route, resp.status_code, resp.text)


@pytest.mark.parametrize("route,page,method,body", RBAC_CASES)
def test_staff_with_page_succeeds(client, db_session, route, page, method, body):
    """Staff granted the page must pass require_page (not 403)."""
    user = _make_staff(db_session, pages=[page])
    c = _authed_client(client, user)
    resp = c.request(method, route, json=body) if body else c.request(method, route)
    assert resp.status_code != 403, (route, resp.status_code, resp.text)
    assert resp.status_code != 401, (route, "auth failed", resp.text)


@pytest.mark.parametrize("route,page,method,body", RBAC_CASES)
def test_admin_bypasses(client, admin_token, route, page, method, body):
    """Admin role bypasses require_page for every domain."""
    client.headers.update({"Authorization": f"Bearer {admin_token}"})
    resp = (
        client.request(method, route, json=body)
        if body
        else client.request(method, route)
    )
    assert resp.status_code != 403, (route, resp.status_code, resp.text)
    assert resp.status_code != 401, (route, "admin auth failed", resp.text)


def test_unauthenticated_gets_401(client):
    """No token -> 401 (auth runs before the page check)."""
    resp = client.get("/api/memberships")
    assert resp.status_code == 401


# ---- reception capability: the Members page assigns memberships and takes
# payment, without carrying the Memberships or Sales pages ----
#
# Reception staff get pages=["members"]: enrol a face, assign/renew a
# membership, collect the money. They must NOT reach the Memberships or Sales
# pages. The write paths those actions need therefore accept `members`
# (require_any_page), while every browse/report path stays on its own page.

_ANY_UUID = "00000000-0000-0000-0000-0000000000ff"

# Routes the assign/renew/collect flow calls. Non-403 is the assertion; a
# missing member or plan legitimately answers 404.
MEMBERS_CAPABILITY_CASES = [
    ("GET", f"/api/memberships?member_id={_ANY_UUID}", None),
    ("GET", "/api/membership-plans", None),
    (
        "POST",
        "/api/memberships",
        {
            "member_id": _ANY_UUID,
            "plan_id": _ANY_UUID,
            "type": "Monthly",
            "start_date": "2026-01-01",
            "end_date": "2026-02-01",
        },
    ),
    (
        "POST",
        "/api/sales",
        {"member_id": _ANY_UUID, "amount": "10.00", "payment_method": "cash"},
    ),
]

# What the Members page must NOT unlock: the memberships ledger, the sales
# ledger and its reports, plan management, and membership edits.
MEMBERS_CAPABILITY_DENIED = [
    ("GET", "/api/memberships", None),  # unfiltered ledger
    ("GET", "/api/sales", None),
    ("GET", "/api/sales/dashboard", None),
    ("GET", "/api/sales/report/summary", None),
    ("GET", "/api/sales/report/export", None),
    (
        "POST",
        "/api/membership-plans",
        {"name": "Sneaky", "duration_days": 30, "price": "1.00"},
    ),
    ("PUT", f"/api/memberships/{_ANY_UUID}", {"status": "active"}),
]


@pytest.mark.parametrize("method,route,body", MEMBERS_CAPABILITY_CASES)
def test_members_page_can_assign_membership_and_take_payment(
    client, db_session, method, route, body
):
    """pages=["members"] must reach the assign/renew/collect writes."""
    user = _make_staff(db_session, pages=["members"])
    c = _authed_client(client, user)
    resp = c.request(method, route, json=body) if body else c.request(method, route)
    assert resp.status_code != 403, (route, resp.status_code, resp.text)
    assert resp.status_code != 401, (route, "auth failed", resp.text)


@pytest.mark.parametrize("method,route,body", MEMBERS_CAPABILITY_DENIED)
def test_members_page_does_not_unlock_memberships_or_sales(
    client, db_session, method, route, body
):
    """pages=["members"] must stay out of both ledgers and plan management."""
    user = _make_staff(db_session, pages=["members"])
    c = _authed_client(client, user)
    resp = c.request(method, route, json=body) if body else c.request(method, route)
    assert resp.status_code == 403, (route, resp.status_code, resp.text)


@pytest.mark.parametrize("method,route,body", MEMBERS_CAPABILITY_CASES)
def test_no_pages_still_denied_on_assignment_routes(
    client, db_session, method, route, body
):
    """require_any_page must not become a hole: pages=[] is still 403."""
    user = _make_staff(db_session, pages=[])
    c = _authed_client(client, user)
    resp = c.request(method, route, json=body) if body else c.request(method, route)
    assert resp.status_code == 403, (route, resp.status_code, resp.text)


# ---- the members router is page-gated, not merely role-gated ----
#
# Every /members route was `require_staff`, so the `members` grant was UI-only:
# any staff token could read, create, edit and delete members, and read the
# biometric photo, whatever the admin unchecked in Settings.

_MEMBER_WRITE_ROUTES = [
    ("POST", "/api/members", {"first_name": "A", "last_name": "B"}),
    ("GET", f"/api/members/{_ANY_UUID}", None),
    ("PUT", f"/api/members/{_ANY_UUID}", {"first_name": "A"}),
    ("DELETE", f"/api/members/{_ANY_UUID}", None),
    ("GET", f"/api/members/{_ANY_UUID}/biometric-status", None),
    ("GET", f"/api/members/{_ANY_UUID}/photo", None),
]


@pytest.mark.parametrize("method,route,body", _MEMBER_WRITE_ROUTES)
def test_member_record_routes_require_the_members_page(
    client, db_session, method, route, body
):
    """A staff token without the Members page must not touch member records."""
    user = _make_staff(db_session, pages=["memberships", "sales", "reports"])
    c = _authed_client(client, user)
    resp = c.request(method, route, json=body) if body else c.request(method, route)
    assert resp.status_code == 403, (route, resp.status_code, resp.text)


@pytest.mark.parametrize("method,route,body", _MEMBER_WRITE_ROUTES)
def test_members_page_reaches_member_record_routes(
    client, db_session, method, route, body
):
    """The Members page still reaches all of them (404 for a bogus id is fine)."""
    user = _make_staff(db_session, pages=["members"])
    c = _authed_client(client, user)
    resp = c.request(method, route, json=body) if body else c.request(method, route)
    assert resp.status_code != 403, (route, resp.status_code, resp.text)
    assert resp.status_code != 401, (route, "auth failed", resp.text)


@pytest.mark.parametrize("page", ["members", "memberships", "reports"])
def test_member_directory_is_readable_by_pages_with_a_member_picker(
    client, db_session, page
):
    """`GET /members` backs the Members list, the Memberships assign picker and
    the Reports-gated dashboard count."""
    user = _make_staff(db_session, pages=[page])
    c = _authed_client(client, user)
    resp = c.get("/api/members")
    assert resp.status_code == 200, (page, resp.status_code, resp.text)


@pytest.mark.parametrize("pages", [[], ["dashboard"], ["cameras"], ["sales"]])
def test_member_directory_denied_without_one_of_those_pages(client, db_session, pages):
    """No member picker on those pages -> no member directory."""
    user = _make_staff(db_session, pages=pages)
    c = _authed_client(client, user)
    resp = c.get("/api/members")
    assert resp.status_code == 403, (pages, resp.status_code, resp.text)


def test_memberships_page_still_browses_unfiltered_ledger(client, db_session):
    """The owning page keeps its own listing — the member_id scope is only
    imposed on a caller who lacks it."""
    user = _make_staff(db_session, pages=["memberships"])
    c = _authed_client(client, user)
    resp = c.get("/api/memberships")
    assert resp.status_code == 200, (resp.status_code, resp.text)


def test_send_report_now_per_user_counter_429(client, db_session):
    """WS-9 (CWE-770): manual report sends are capped at 2/hour per user via
    the Redis `report-send:{user_id}` counter — the 3rd call must 429.

    Not a slowapi test: the limiter uses in-memory storage that accumulates
    across the suite, so we assert the per-user Redis counter instead.
    """
    import redis

    from core.config import settings

    r = redis.from_url(settings.REDIS_URL, decode_responses=True)
    user = _make_staff(db_session, pages=["reports"])
    key = f"report-send:{str(user.id)}"
    r.delete(key)
    try:
        c = _authed_client(client, user)
        resp1 = c.post("/api/reports-email/send-now")
        assert resp1.status_code == 200, resp1.text
        resp2 = c.post("/api/reports-email/send-now")
        assert resp2.status_code == 200, resp2.text
        resp3 = c.post("/api/reports-email/send-now")
        assert resp3.status_code == 429, resp3.text
        assert "Report already sent recently" in resp3.json()["detail"]
    finally:
        r.delete(key)


# ---- deny-by-default permissions (CWE-269) ----


def test_new_user_without_permissions_defaults_to_no_pages(db_session):
    """
    A user created with no explicit permissions must get {"pages": []}
    (deny-by-default), NOT {"pages": ["all"]}. This is the model-level fix
    for privilege-management.default-staff-all-pages.
    """
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"nopages-{suffix}",
        email=f"nopages-{suffix}@example.com",
        password_hash=get_password_hash("secret123"),
        role="staff",
        is_active=True,
        # permissions intentionally omitted
    )
    db_session.add(user)
    db_session.flush()
    assert user.permissions == {"pages": []}, user.permissions
    # Route-level enforcement for a {"pages": []} caller is covered by
    # test_staff_without_page_gets_403 (via _make_staff(pages=[])).


def test_create_user_api_denies_by_default(client, admin_token, db_session):
    """
    POST /api/users with no permissions payload must create a staff user with
    permissions {"pages": []}, not all pages (the api/users.py:75 fix).
    """
    from models.user import User as UserModel

    client.headers.update({"Authorization": f"Bearer {admin_token}"})
    suffix = uuid.uuid4().hex[:8]
    resp = client.post(
        "/api/users",
        json={
            "username": f"created-{suffix}",
            "email": f"created-{suffix}@example.com",
            "password": "supersecret123",
            "role": "staff",
            "is_active": True,
            # permissions intentionally omitted
        },
    )
    assert resp.status_code == 201, (resp.status_code, resp.text)
    created = (
        db_session.query(UserModel).filter_by(username=f"created-{suffix}").first()
    )
    assert created is not None
    assert created.permissions == {"pages": []}, created.permissions
