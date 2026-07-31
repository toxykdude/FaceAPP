"""
Session-revocation tests (S6, CWE-613).

A stolen/old JWT must stop working the moment the user's password is changed
or reset. Enforced by a per-user token_version epoch stamped into issued JWTs
("ver") and checked in get_current_user. Bumping token_version (on password
change/reset) invalidates every prior token.

Uses dedicated users (not the shared admin) so a token_version bump never
bleeds into other tests.
"""

import uuid

from core.security import create_access_token, get_password_hash
from models.user import User


def _make_user(db_session, **over):
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"revok-{suffix}",
        email=f"revok-{suffix}@example.com",
        password_hash=get_password_hash("OldPass123"),
        role="staff",
        is_active=True,
        permissions={"pages": []},
    )
    for k, v in over.items():
        setattr(user, k, v)
    db_session.add(user)
    db_session.commit()
    return user


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


class TestSessionRevocation:
    def test_old_token_revoked_after_version_bump(self, client, db_session):
        """After token_version is bumped (password change/reset), a JWT issued
        before the bump is rejected with 401 by get_current_user."""
        user = _make_user(db_session)
        old_token = create_access_token(data={"sub": str(user.id), "ver": 0})

        # Before the bump: token is valid -> not a 401 (403 from require_page is
        # fine; the point is the token itself is accepted).
        before = client.get("/api/memberships", headers=_auth(old_token))
        assert before.status_code != 401, before.text

        # Simulate the password-change/reset bump.
        user.token_version = 1
        db_session.commit()

        # After the bump: the old token is now revoked -> 401.
        after = client.get("/api/memberships", headers=_auth(old_token))
        assert after.status_code == 401, after.text
        assert "revok" in after.json()["detail"].lower()

    def test_new_token_after_bump_works(self, client, db_session):
        """A freshly-issued token carrying the new version is accepted."""
        user = _make_user(db_session, token_version=2)
        fresh = create_access_token(data={"sub": str(user.id), "ver": 2})

        resp = client.get("/api/memberships", headers=_auth(fresh))
        assert resp.status_code != 401, resp.text  # accepted (403 ok, not revoked)

    def test_change_password_bumps_version(self, client, db_session, admin_token):
        """POST /api/users/{id}/change-password must increment token_version."""
        user = _make_user(db_session)
        before = user.token_version

        resp = client.post(
            f"/api/users/{user.id}/change-password",
            headers=_auth(admin_token),
            json={"new_password": "BrandNewPass456"},
        )
        assert resp.status_code == 200, resp.text

        db_session.expire_all()
        after = db_session.query(User).filter_by(id=user.id).first().token_version
        assert after == before + 1, (before, after)
