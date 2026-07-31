"""Authorization tests for the sync API endpoints.

Spec context: ``/api/sync/pull`` and ``/api/sync/push`` used to be protected
ONLY by ``require_staff`` (a coarse role check). That let any staff account
pull raw ``users`` rows (administrator password hashes), decrypted RTSP
credentials from ``cameras``, and ``access_events``, and push
INSERT/UPDATE/DELETE on ``cameras`` / ``memberships``.

These tests pin the per-table RBAC gate added in ``api/sync.py``:
- Admin bypasses everything (can still sync ``users`` / ``cameras``).
- Staff must hold the matching page permission; admin-only tables
  (``users``, ``cameras``, ``access_events``) return 403 for non-admins.
- Batches fail fast: if ANY op targets an unauthorized table, the whole
  batch is rejected with 403 before any row is mutated.
"""

import uuid

import pytest

from core.security import create_access_token
from models.user import User, UserRole
from models.member import Member
from models.camera import Camera

PULL_URL = "/api/sync/pull"
PUSH_URL = "/api/sync/push"
# Far in the past so every row is considered "changed since last_sync".
EPOCH = "2000-01-01T00:00:00Z"


# --- helpers ----------------------------------------------------------------


def _make_staff(db_session, pages):
    """Create an active staff user with the given ``permissions.pages`` list."""
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"staff-{suffix}",
        email=f"staff-{suffix}@example.com",
        password_hash="not-a-real-hash",
        role=UserRole.STAFF.value,
        is_active=True,
        permissions={"pages": list(pages)},
    )
    db_session.add(user)
    db_session.flush()
    return user


def _staff_headers(user):
    """Bearer headers for a given user."""
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


def _pull(client, headers, tables):
    return client.post(
        PULL_URL, headers=headers, json={"last_sync_at": EPOCH, "tables": tables}
    )


# --- pull: admin -----------------------------------------------------------


class TestSyncPullAdmin:
    def test_admin_can_pull_users_including_password_hash(
        self, client, auth_headers, admin_user
    ):
        resp = _pull(client, auth_headers, ["users"])
        assert resp.status_code == 200
        data = resp.json()
        rows = data.get("users", [])
        assert rows, "expected at least one user row"
        # Every user row serializes the sensitive password_hash column.
        assert all("password_hash" in row for row in rows)
        # The known admin hash is present in the admin response.
        assert any(r["password_hash"] == admin_user.password_hash for r in rows)

    def test_admin_can_pull_cameras(self, client, auth_headers):
        resp = _pull(client, auth_headers, ["cameras"])
        assert resp.status_code == 200
        assert "cameras" in resp.json()


# --- pull: staff without any pages -----------------------------------------


class TestSyncPullStaffNoPages:
    @pytest.fixture
    def headers(self, db_session):
        return _staff_headers(_make_staff(db_session, []))

    def test_pull_users_forbidden(self, client, headers):
        assert _pull(client, headers, ["users"]).status_code == 403

    def test_pull_cameras_forbidden(self, client, headers):
        assert _pull(client, headers, ["cameras"]).status_code == 403

    def test_pull_access_events_forbidden(self, client, headers):
        assert _pull(client, headers, ["access_events"]).status_code == 403


# --- pull: staff with `members` page ---------------------------------------


class TestSyncPullStaffMembersPage:
    @pytest.fixture
    def headers(self, db_session):
        return _staff_headers(_make_staff(db_session, ["members"]))

    def test_pull_members_allowed_with_rows(self, client, headers, sample_member):
        resp = _pull(client, headers, ["members"])
        assert resp.status_code == 200
        rows = resp.json().get("members", [])
        assert any(r["id"] == str(sample_member.id) for r in rows)

    def test_pull_users_forbidden(self, client, headers):
        assert _pull(client, headers, ["users"]).status_code == 403

    def test_pull_cameras_forbidden(self, client, headers):
        assert _pull(client, headers, ["cameras"]).status_code == 403


# --- pull: staff with `memberships` page -----------------------------------


class TestSyncPullStaffMembershipsPage:
    @pytest.fixture
    def headers(self, db_session):
        return _staff_headers(_make_staff(db_session, ["memberships"]))

    def test_pull_memberships_and_plans_allowed(self, client, headers):
        resp = _pull(client, headers, ["memberships", "membership_plans"])
        assert resp.status_code == 200
        body = resp.json()
        assert "memberships" in body
        assert "membership_plans" in body

    def test_pull_users_forbidden(self, client, headers):
        assert _pull(client, headers, ["users"]).status_code == 403


# --- pull: sensitive data never exposed to staff ---------------------------


class TestSensitiveDataNotExposed:
    def test_staff_pull_users_never_returns_hash(self, client, db_session, admin_user):
        headers = _staff_headers(_make_staff(db_session, ["members"]))
        resp = _pull(client, headers, ["users"])
        assert resp.status_code == 403
        # The 403 body must not leak the password hash.
        assert admin_user.password_hash not in resp.text

    def test_admin_pull_users_returns_hash(self, client, auth_headers, admin_user):
        resp = _pull(client, auth_headers, ["users"])
        assert resp.status_code == 200
        assert admin_user.password_hash in resp.text


# --- push: authorization ---------------------------------------------------


class TestSyncPushAuthorization:
    def test_unauthenticated_push_returns_401(self, client):
        resp = client.post(
            PUSH_URL, json={"operations": [{"table": "members", "operation": "INSERT"}]}
        )
        assert resp.status_code == 401

    def test_admin_can_push_camera_op(self, client, auth_headers):
        marker = f"cam-admin-{uuid.uuid4().hex[:8]}"
        resp = client.post(
            PUSH_URL,
            headers=auth_headers,
            json={
                "operations": [
                    {
                        "table": "cameras",
                        "operation": "INSERT",
                        "data": {"name": marker, "rtsp_url": "rtsp://x"},
                    }
                ]
            },
        )
        # Admin bypasses the gate — must not be a 403.
        assert resp.status_code != 403

    def test_staff_no_pages_camera_insert_forbidden(self, client, db_session):
        headers = _staff_headers(_make_staff(db_session, []))
        marker = f"cam-ins-{uuid.uuid4().hex[:8]}"
        resp = client.post(
            PUSH_URL,
            headers=headers,
            json={
                "operations": [
                    {
                        "table": "cameras",
                        "operation": "INSERT",
                        "data": {"name": marker, "rtsp_url": "rtsp://x"},
                    }
                ]
            },
        )
        assert resp.status_code == 403
        # Fail-fast means no row was ever created.
        assert db_session.query(Camera).filter(Camera.name == marker).count() == 0

    def test_staff_no_pages_camera_update_forbidden(self, client, db_session):
        headers = _staff_headers(_make_staff(db_session, []))
        resp = client.post(
            PUSH_URL,
            headers=headers,
            json={
                "operations": [
                    {
                        "table": "cameras",
                        "operation": "UPDATE",
                        "id": str(uuid.uuid4()),
                        "data": {"name": "should-not-apply"},
                    }
                ]
            },
        )
        assert resp.status_code == 403

    def test_staff_no_pages_camera_delete_forbidden(self, client, db_session):
        headers = _staff_headers(_make_staff(db_session, []))
        resp = client.post(
            PUSH_URL,
            headers=headers,
            json={
                "operations": [
                    {
                        "table": "cameras",
                        "operation": "DELETE",
                        "id": str(uuid.uuid4()),
                    }
                ]
            },
        )
        assert resp.status_code == 403

    def test_staff_members_page_can_push_member_insert(self, client, db_session):
        headers = _staff_headers(_make_staff(db_session, ["members"]))
        email = f"ok-{uuid.uuid4().hex[:8]}@example.com"
        resp = client.post(
            PUSH_URL,
            headers=headers,
            json={
                "operations": [
                    {
                        "table": "members",
                        "operation": "INSERT",
                        "data": {
                            "first_name": "Sync",
                            "last_name": "User",
                            "email": email,
                        },
                    }
                ]
            },
        )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert results[0]["status"] == "success"

    def test_batch_with_unauthorized_op_fails_fast(self, client, db_session):
        # Staff holds `members` but NOT cameras/admin.
        headers = _staff_headers(_make_staff(db_session, ["members"]))
        member_email = f"batch-{uuid.uuid4().hex[:8]}@example.com"
        resp = client.post(
            PUSH_URL,
            headers=headers,
            json={
                "operations": [
                    {
                        "table": "cameras",
                        "operation": "INSERT",
                        "data": {"name": "nope", "rtsp_url": "rtsp://x"},
                    },
                    {
                        "table": "members",
                        "operation": "INSERT",
                        "data": {
                            "first_name": "Batch",
                            "last_name": "Member",
                            "email": member_email,
                        },
                    },
                ]
            },
        )
        # The whole batch is rejected because of the cameras op...
        assert resp.status_code == 403
        # ...and the authorized members op MUST NOT be applied (fail fast).
        assert (
            db_session.query(Member).filter(Member.email == member_email).count() == 0
        )
