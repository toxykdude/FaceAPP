"""
Security tests for the biometric enrollment path (WS-5):

- Consent enforcement (Ley 1581): enrollment must be refused when the member
  has no recorded biometric consent (missing-authorization.biometric-consent).
- Biometric audit durability: a template deletion must write a durable audit
  row in the SAME transaction (audit-integrity.biometric-audit).

The enroll *positive* path needs torch/face models (absent in the backend
test venv), so it is not exercised here; the consent check runs before face
detection, so denial IS testable, and delete needs no face models.
"""

import uuid
from unittest.mock import AsyncMock

import pytest

import api.enrollment as enrollment_module
from core.encryption import encrypt_template
from core.security import create_access_token
from models.audit_log import AuditLog
from models.biometric import BiometricTemplate
from models.member import Member


@pytest.fixture
def admin_auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def _member_without_consent(db_session):
    """A member with NO biometric consent recorded (consent_given_at is None)."""
    member = Member(
        first_name="NoConsent",
        last_name="Tester",
        email=f"noconsent-{uuid.uuid4().hex[:8]}@example.com",
        phone="555-0100",
        status="active",
        # consent_given_at intentionally omitted (None)
    )
    db_session.add(member)
    db_session.flush()
    return member


def _member_with_consent_and_template(db_session):
    """A consented member with an existing biometric template (for delete tests)."""
    member = Member(
        first_name="Consented",
        last_name="Tester",
        email=f"consented-{uuid.uuid4().hex[:8]}@example.com",
        phone="555-0200",
        status="active",
        facial_data_enrolled=True,
    )
    member.consent_given_at = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    )
    db_session.add(member)
    db_session.flush()

    template = BiometricTemplate(
        member_id=str(member.id),
        template_data=encrypt_template(b'{"embedding": [0.0]}'),
        quality_score=0.9,
        encryption_key_id="v1",
    )
    db_session.add(template)
    db_session.commit()
    return member


class TestBiometricConsent:
    def test_upload_enroll_refused_without_consent(
        self, client, admin_auth_headers, db_session, monkeypatch
    ):
        """POST /enrollment/{id}/enroll (upload) -> 403 when no consent."""
        monkeypatch.setattr(enrollment_module, "notify_cv_reload", AsyncMock())
        member = _member_without_consent(db_session)

        resp = client.post(
            f"/api/enrollment/{member.id}/enroll",
            headers=admin_auth_headers,
            files={"image": ("face.jpg", b"fake-bytes", "image/jpeg")},
        )
        assert resp.status_code == 403, (resp.status_code, resp.text)
        assert "consent" in resp.json()["detail"].lower()

    def test_camera_enroll_refused_without_consent(
        self, client, admin_auth_headers, db_session, monkeypatch
    ):
        """POST /enrollment/{id}/enroll/camera -> 403 when no consent."""
        monkeypatch.setattr(enrollment_module, "notify_cv_reload", AsyncMock())
        member = _member_without_consent(db_session)

        resp = client.post(
            f"/api/enrollment/{member.id}/enroll/camera",
            headers=admin_auth_headers,
            json={"camera_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 403, (resp.status_code, resp.text)
        assert "consent" in resp.json()["detail"].lower()


class TestBiometricAudit:
    def test_delete_enrollment_writes_durable_audit(
        self, client, admin_auth_headers, db_session, monkeypatch
    ):
        """DELETE /enrollment/{id}/enroll must commit a biometric_delete audit
        row in the same transaction as the deletion."""
        monkeypatch.setattr(enrollment_module, "notify_cv_reload", AsyncMock())
        member = _member_with_consent_and_template(db_session)

        before = (
            db_session.query(AuditLog)
            .filter_by(action="biometric_delete", resource_id=str(member.id))
            .count()
        )

        resp = client.delete(
            f"/api/enrollment/{member.id}/enroll", headers=admin_auth_headers
        )
        assert resp.status_code == 200, (resp.status_code, resp.text)

        # The audit row must be durably committed (not just flushed).
        db_session.expire_all()
        after = (
            db_session.query(AuditLog)
            .filter_by(action="biometric_delete", resource_id=str(member.id))
            .count()
        )
        assert after == before + 1, "biometric_delete audit row was not committed"

        # And the template is gone.
        remaining = (
            db_session.query(BiometricTemplate)
            .filter_by(member_id=str(member.id))
            .count()
        )
        assert remaining == 0
