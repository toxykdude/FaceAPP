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
