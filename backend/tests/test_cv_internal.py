"""
Tests for the DISPLAY vs ACCESS predicate split in backend/api/cv_internal.py.

DISPLAY (sync_templates): status='active' AND end_date>=today — NO
start_date filter. Furthest end_date wins; ties break on created_at then id.

ACCESS (get_member_membership): status='active' AND start_date<=today AND
end_date>=today. This predicate is unchanged — the tests below are
approval tests documenting/preserving current (already correct) behavior.
"""

import json
import uuid
from datetime import date, timedelta, datetime, timezone

import pytest

from core.config import settings
from core.encryption import encrypt_template
from models.biometric import BiometricTemplate
from models.membership import Membership, MembershipStatus
from models.member import Member


@pytest.fixture
def internal_headers():
    return {"X-Internal-Secret": settings.INTERNAL_API_SECRET}


def make_template(db_session, member):
    embedding = json.dumps([0.1] * 8).encode("utf-8")
    template = BiometricTemplate(
        member_id=member.id,
        template_data=encrypt_template(embedding),
        quality_score=0.95,
    )
    db_session.add(template)
    db_session.flush()
    return template


def make_membership(
    db_session,
    member,
    start_offset,
    end_offset,
    created_at=None,
    access_rules=None,
    membership_id=None,
):
    today = date.today()
    kwargs = dict(
        member_id=member.id,
        type="monthly",
        start_date=today + timedelta(days=start_offset),
        end_date=today + timedelta(days=end_offset),
        price=29.99,
        status=MembershipStatus.ACTIVE.value,
        access_rules=access_rules or {},
    )
    if membership_id is not None:
        kwargs["id"] = membership_id
    if created_at is not None:
        kwargs["created_at"] = created_at
    m = Membership(**kwargs)
    db_session.add(m)
    db_session.flush()
    return m


class TestDisplayFurthestExpiration:
    """DISPLAY must show the furthest paid expiration, even when that
    membership has not started yet — display never gates entry."""

    def test_future_paid_renewal_is_displayed_even_when_not_started(
        self, client, db_session, sample_member, internal_headers
    ):
        make_template(db_session, sample_member)
        make_membership(db_session, sample_member, start_offset=-10, end_offset=5)
        future = make_membership(
            db_session, sample_member, start_offset=20, end_offset=50
        )

        resp = client.get("/api/cv/templates", headers=internal_headers)
        assert resp.status_code == 200

        entry = next(
            t
            for t in resp.json()["templates"]
            if t["member_id"] == str(sample_member.id)
        )
        assert entry["membership_end_date"] == future.end_date.isoformat()
        assert entry["has_active_membership"] is True

    def test_tie_break_by_created_at_when_end_dates_match(
        self, client, db_session, sample_member, internal_headers
    ):
        now = datetime.now(timezone.utc)
        make_membership(
            db_session,
            sample_member,
            start_offset=0,
            end_offset=40,
            created_at=now - timedelta(hours=1),
            access_rules={"marker": "older"},
        )
        make_membership(
            db_session,
            sample_member,
            start_offset=0,
            end_offset=40,
            created_at=now,
            access_rules={"marker": "newer"},
        )
        make_template(db_session, sample_member)

        resp = client.get("/api/cv/templates", headers=internal_headers)
        entry = next(
            t
            for t in resp.json()["templates"]
            if t["member_id"] == str(sample_member.id)
        )
        assert entry["access_rules"]["marker"] == "newer"

    def test_tie_break_by_id_when_end_date_and_created_at_match(
        self, client, db_session, sample_member, internal_headers
    ):
        same_created = datetime.now(timezone.utc)
        make_membership(
            db_session,
            sample_member,
            start_offset=0,
            end_offset=40,
            created_at=same_created,
            access_rules={"marker": "lower-id"},
            membership_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        )
        make_membership(
            db_session,
            sample_member,
            start_offset=0,
            end_offset=40,
            created_at=same_created,
            access_rules={"marker": "higher-id"},
            membership_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        )
        make_template(db_session, sample_member)

        resp = client.get("/api/cv/templates", headers=internal_headers)
        entry = next(
            t
            for t in resp.json()["templates"]
            if t["member_id"] == str(sample_member.id)
        )
        assert entry["access_rules"]["marker"] == "higher-id"

    def test_cross_member_isolation(
        self, client, db_session, sample_member, internal_headers
    ):
        other = Member(
            first_name="Other",
            last_name="Member",
            email=f"other{uuid.uuid4().hex[:8]}@example.com",
            phone="555-0200",
            status="active",
        )
        db_session.add(other)
        db_session.flush()

        make_template(db_session, sample_member)
        make_template(db_session, other)
        mine = make_membership(
            db_session, sample_member, start_offset=-5, end_offset=15
        )
        theirs = make_membership(db_session, other, start_offset=-5, end_offset=60)

        resp = client.get("/api/cv/templates", headers=internal_headers)
        by_member = {t["member_id"]: t for t in resp.json()["templates"]}

        assert (
            by_member[str(sample_member.id)]["membership_end_date"]
            == mine.end_date.isoformat()
        )
        assert (
            by_member[str(other.id)]["membership_end_date"]
            == theirs.end_date.isoformat()
        )


class TestAccessWindowUnchanged:
    """ACCESS (get_member_membership) predicate is unchanged — approval
    tests documenting current (already correct) behavior per design.md."""

    def test_pre_start_membership_denies_access(
        self, client, db_session, sample_member, internal_headers
    ):
        make_membership(db_session, sample_member, start_offset=5, end_offset=40)

        resp = client.get(
            f"/api/cv/members/{sample_member.id}/membership", headers=internal_headers
        )
        assert resp.status_code == 200
        assert resp.json()["has_active"] is False

    def test_start_boundary_grants_access(
        self, client, db_session, sample_member, internal_headers
    ):
        m = make_membership(db_session, sample_member, start_offset=0, end_offset=30)

        resp = client.get(
            f"/api/cv/members/{sample_member.id}/membership", headers=internal_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_active"] is True
        assert data["membership"]["id"] == str(m.id)
