"""
Audit-durability tests (WS-8 audit-integrity, CWE-778).

A protected mutation (member create/update/delete, member import, staff login)
must leave a DURABLE audit row -- committed in the same transaction as the
mutation, not just flushed into a transaction that never commits. log_action
flushes by design, so the fix is to call it BEFORE the endpoint's db.commit().
"""

import uuid

from core.security import get_password_hash
from models.audit_log import AuditLog
from models.user import User


def _audited(db_session, **filt):
    db_session.expire_all()
    return db_session.query(AuditLog).filter_by(**filt).first()


class TestMemberAuditDurability:
    def test_create_is_audited(self, client, auth_headers, db_session):
        resp = client.post(
            "/api/members",
            headers=auth_headers,
            json={
                "first_name": "AuditCreate",
                "id_number": f"ID-{uuid.uuid4().hex[:6]}",
            },
        )
        assert resp.status_code == 201, resp.text
        member_id = resp.json()["id"]
        assert _audited(db_session, action="create", resource_id=member_id) is not None

    def test_update_is_audited(self, client, auth_headers, db_session, sample_member):
        resp = client.put(
            f"/api/members/{sample_member.id}",
            headers=auth_headers,
            json={"first_name": "AuditUpdate"},
        )
        assert resp.status_code == 200, resp.text
        assert (
            _audited(
                db_session,
                action="update",
                resource_id=str(sample_member.id),
            )
            is not None
        )

    def test_delete_is_audited(self, client, auth_headers, db_session, sample_member):
        mid = str(sample_member.id)
        resp = client.delete(f"/api/members/{mid}", headers=auth_headers)
        assert resp.status_code == 204, resp.text
        assert _audited(db_session, action="delete", resource_id=mid) is not None


class TestLoginAuditDurability:
    def test_login_is_audited(self, client, db_session):
        suffix = uuid.uuid4().hex[:8]
        user = User(
            username=f"login-{suffix}",
            email=f"login-{suffix}@example.com",
            password_hash=get_password_hash("LoginPass123"),
            role="staff",
            is_active=True,
            permissions={"pages": []},
        )
        db_session.add(user)
        db_session.commit()

        resp = client.post(
            "/api/auth/login",
            json={"username": f"login-{suffix}", "password": "LoginPass123"},
        )
        assert resp.status_code == 200, resp.text
        # The login audit row must be durably committed.
        assert _audited(db_session, action="login", user_id=str(user.id)) is not None
