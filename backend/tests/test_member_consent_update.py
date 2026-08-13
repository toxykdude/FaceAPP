"""
Tests for post-creation biometric consent changes on PUT /members/{id}.

Background: `consent_given` was only honoured by POST /members. It was absent
from the `MemberUpdate` schema, so Pydantic silently dropped it and a member
created without consent could NEVER be granted consent afterwards — the
enrollment endpoint then refused them forever with
"Biometric consent required before enrollment".

`MemberResponse` also exposed only `consent_given_at`, so the admin form's
checkbox (which reads `consent_given`) rendered unchecked even for consented
members.

Ley 1581 also grants a withdrawal right, so revoking consent must clear the
timestamp AND destroy the derived biometric data — leaving the template behind
would keep the kiosk recognising a member whose consent is recorded as
withdrawn.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

import api.members as members_module
from core.encryption import encrypt_template
from models.audit_log import AuditLog
from models.biometric import BiometricTemplate
from models.member import Member


@pytest.fixture
def no_cv_notify(monkeypatch):
    """Stub the best-effort CV invalidation so tests make no network calls."""
    stub = AsyncMock()
    monkeypatch.setattr(members_module, "notify_cv_invalidation", stub)
    return stub


def _member(db_session, *, consented=False, enrolled=False):
    member = Member(
        first_name="Consent",
        last_name="Tester",
        email=f"consent-{uuid.uuid4().hex[:8]}@example.com",
        phone="555-0300",
        status="active",
        facial_data_enrolled=enrolled,
        consent_given_at=(
            datetime.now(timezone.utc) - timedelta(days=7) if consented else None
        ),
    )
    db_session.add(member)
    db_session.flush()

    if enrolled:
        db_session.add(
            BiometricTemplate(
                member_id=str(member.id),
                template_data=encrypt_template(b'{"embedding": [0.0]}'),
                quality_score=0.9,
                encryption_key_id="v1",
            )
        )
    db_session.commit()
    return member


class TestConsentGrant:
    def test_put_grants_consent_to_member_created_without_it(
        self, auth_client, db_session, no_cv_notify
    ):
        """The reported bug: checking the box on an existing member must stick."""
        member = _member(db_session, consented=False)
        assert member.consent_given_at is None

        resp = auth_client.put(
            f"/api/members/{member.id}", json={"consent_given": True}
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["consent_given"] is True
        db_session.refresh(member)
        assert member.consent_given_at is not None

    def test_response_exposes_consent_given_boolean(
        self, auth_client, db_session, no_cv_notify
    ):
        """The admin checkbox reads `consent_given`; the API must serve it."""
        consented = _member(db_session, consented=True)
        plain = _member(db_session, consented=False)

        assert (
            auth_client.get(f"/api/members/{consented.id}").json()["consent_given"]
            is True
        )
        assert (
            auth_client.get(f"/api/members/{plain.id}").json()["consent_given"] is False
        )

    def test_regranting_preserves_the_original_consent_timestamp(
        self, auth_client, db_session, no_cv_notify
    ):
        """Consent is dated evidence — re-saving the form must not re-date it."""
        member = _member(db_session, consented=True)
        original = member.consent_given_at

        resp = auth_client.put(
            f"/api/members/{member.id}", json={"consent_given": True}
        )

        assert resp.status_code == 200, resp.text
        db_session.refresh(member)
        assert member.consent_given_at == original

    def test_enrollment_no_longer_refused_after_consent_is_granted(
        self, auth_client, db_session, no_cv_notify
    ):
        """End-to-end regression: the 403 the user hit must be gone.

        The enroll positive path needs face models absent from the test venv,
        so this asserts only that the request gets PAST the consent gate.
        """
        member = _member(db_session, consented=False)
        auth_client.put(f"/api/members/{member.id}", json={"consent_given": True})

        resp = auth_client.post(
            f"/api/enrollment/{member.id}/enroll",
            files={"image": ("face.jpg", b"not-a-real-image", "image/jpeg")},
        )

        assert resp.status_code != 403
        assert "consent" not in resp.text.lower()

    def test_update_without_consent_field_leaves_consent_untouched(
        self, auth_client, db_session, no_cv_notify
    ):
        """A phone edit must not silently revoke biometric consent."""
        member = _member(db_session, consented=True, enrolled=True)
        original = member.consent_given_at

        resp = auth_client.put(f"/api/members/{member.id}", json={"phone": "555-9999"})

        assert resp.status_code == 200, resp.text
        db_session.refresh(member)
        assert member.consent_given_at == original
        assert member.facial_data_enrolled is True
        assert (
            db_session.query(BiometricTemplate)
            .filter(BiometricTemplate.member_id == str(member.id))
            .count()
            == 1
        )


class TestConsentRevocation:
    def test_revoking_consent_destroys_the_biometric_template(
        self, auth_client, db_session, no_cv_notify
    ):
        """Ley 1581 withdrawal: the derived biometric data must go with it."""
        member = _member(db_session, consented=True, enrolled=True)

        resp = auth_client.put(
            f"/api/members/{member.id}", json={"consent_given": False}
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["consent_given"] is False
        db_session.refresh(member)
        assert member.consent_given_at is None
        assert member.facial_data_enrolled is False
        assert (
            db_session.query(BiometricTemplate)
            .filter(BiometricTemplate.member_id == str(member.id))
            .count()
            == 0
        )

    def test_revocation_writes_a_durable_audit_row(
        self, auth_client, db_session, no_cv_notify
    ):
        """Destroying biometric data is an auditable act."""
        member = _member(db_session, consented=True, enrolled=True)

        auth_client.put(f"/api/members/{member.id}", json={"consent_given": False})

        rows = (
            db_session.query(AuditLog)
            .filter(
                AuditLog.action == "biometric_consent_revoked",
                AuditLog.resource_id == str(member.id),
            )
            .all()
        )
        assert len(rows) == 1

    def test_revocation_invalidates_the_cv_cache(
        self, auth_client, db_session, no_cv_notify
    ):
        """A stale CV cache would keep granting entry after revocation."""
        member = _member(db_session, consented=True, enrolled=True)

        auth_client.put(f"/api/members/{member.id}", json={"consent_given": False})

        no_cv_notify.assert_awaited_with(str(member.id))

    def test_revoking_without_an_enrollment_is_a_no_op_on_templates(
        self, auth_client, db_session, no_cv_notify
    ):
        """Consented but never enrolled — must clear cleanly, not 500."""
        member = _member(db_session, consented=True, enrolled=False)

        resp = auth_client.put(
            f"/api/members/{member.id}", json={"consent_given": False}
        )

        assert resp.status_code == 200, resp.text
        db_session.refresh(member)
        assert member.consent_given_at is None

    def test_revoking_when_never_consented_is_idempotent(
        self, auth_client, db_session, no_cv_notify
    ):
        """No consent to withdraw — no audit row, no error."""
        member = _member(db_session, consented=False)

        resp = auth_client.put(
            f"/api/members/{member.id}", json={"consent_given": False}
        )

        assert resp.status_code == 200, resp.text
        assert (
            db_session.query(AuditLog)
            .filter(
                AuditLog.action == "biometric_consent_revoked",
                AuditLog.resource_id == str(member.id),
            )
            .count()
            == 0
        )
