"""Tests for membership endpoints."""

import uuid
import pytest
from decimal import Decimal
from datetime import date, timedelta
from unittest.mock import AsyncMock

import api.memberships as memberships_module

from models.membership import MembershipPlan


@pytest.fixture
def sample_plan(db_session):
    """Sample membership plan (WS-4b: price/end_date derive from it)."""
    plan = MembershipPlan(
        name="Monthly Plan",
        duration_days=30,
        price=Decimal("49.99"),
        is_active=True,
    )
    db_session.add(plan)
    db_session.flush()
    return plan


@pytest.fixture
def second_plan(db_session):
    """Second plan with a different price/duration (for plan-change tests)."""
    plan = MembershipPlan(
        name="Quarterly Plan",
        duration_days=90,
        price=Decimal("129.99"),
        is_active=True,
    )
    db_session.add(plan)
    db_session.flush()
    return plan


class TestMembershipCreate:
    """Test membership creation (WS-4b: price always derived from the plan)."""

    def test_create_membership_price_derived_from_plan(
        self, client, auth_headers, sample_member, sample_plan
    ):
        """Creating with a plan returns the plan's price even when the client
        also sends a bogus `price` — the client price is ignored."""
        response = client.post(
            "/api/memberships",
            headers=auth_headers,
            json={
                "member_id": str(sample_member.id),
                "plan_id": str(sample_plan.id),
                "type": "monthly",
                "start_date": str(date.today()),
                "end_date": str(date.today() + timedelta(days=30)),
                "price": 1.00,  # must be ignored -> plan.price used
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "active"
        assert data["type"] == "monthly"
        assert data["plan_id"] == str(sample_plan.id)
        assert float(data["price"]) == 49.99  # plan.price, not the client's 1.00

    def test_create_derives_end_date_from_plan(
        self, client, auth_headers, sample_member, sample_plan
    ):
        """No end_date sent -> end_date derived as start + plan.duration_days,
        mirroring the portal webhook renewal math."""
        start = date.today()
        response = client.post(
            "/api/memberships",
            headers=auth_headers,
            json={
                "member_id": str(sample_member.id),
                "plan_id": str(sample_plan.id),
                "type": "monthly",
                "start_date": str(start),
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert date.fromisoformat(data["end_date"]) == start + timedelta(days=30)
        assert float(data["price"]) == 49.99

    def test_create_requires_plan(self, client, auth_headers, sample_member):
        """plan_id is now required — omitting it is a validation error."""
        response = client.post(
            "/api/memberships",
            headers=auth_headers,
            json={
                "member_id": str(sample_member.id),
                "type": "monthly",
                "start_date": str(date.today()),
                "end_date": str(date.today() + timedelta(days=30)),
            },
        )
        assert response.status_code == 422

    def test_create_unknown_plan_404(self, client, auth_headers, sample_member):
        """Unknown plan_id -> 404 (price cannot be derived)."""
        response = client.post(
            "/api/memberships",
            headers=auth_headers,
            json={
                "member_id": str(sample_member.id),
                "plan_id": str(uuid.uuid4()),
                "type": "monthly",
                "start_date": str(date.today()),
                "end_date": str(date.today() + timedelta(days=30)),
            },
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Plan not found"


class TestMembershipUpdate:
    """Test membership update (WS-4b: price re-derived on plan change)."""

    def _create(self, client, auth_headers, member_id, plan_id):
        resp = client.post(
            "/api/memberships",
            headers=auth_headers,
            json={
                "member_id": str(member_id),
                "plan_id": str(plan_id),
                "type": "monthly",
                "start_date": str(date.today()),
                "end_date": str(date.today() + timedelta(days=30)),
            },
        )
        assert resp.status_code == 201
        return resp.json()

    def test_update_plan_change_rederives_price(
        self, client, auth_headers, sample_member, sample_plan, second_plan
    ):
        """Changing plan_id re-derives the price from the new plan."""
        membership = self._create(
            client, auth_headers, sample_member.id, sample_plan.id
        )
        assert float(membership["price"]) == 49.99

        resp = client.put(
            f"/api/memberships/{membership['id']}",
            headers=auth_headers,
            json={"plan_id": str(second_plan.id)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan_id"] == str(second_plan.id)
        assert float(data["price"]) == 129.99  # new plan's price, not the old 49.99

    def test_update_ignores_client_price(
        self, client, auth_headers, sample_member, sample_plan
    ):
        """A payload with a bogus `price` leaves the derived price unchanged."""
        membership = self._create(
            client, auth_headers, sample_member.id, sample_plan.id
        )
        assert float(membership["price"]) == 49.99

        resp = client.put(
            f"/api/memberships/{membership['id']}",
            headers=auth_headers,
            json={"price": 1.00},  # unknown field -> dropped by the schema
        )
        assert resp.status_code == 200
        assert float(resp.json()["price"]) == 49.99

    def test_update_unknown_plan_404(
        self, client, auth_headers, sample_member, sample_plan
    ):
        """Updating to an unknown plan_id -> 404."""
        membership = self._create(
            client, auth_headers, sample_member.id, sample_plan.id
        )
        resp = client.put(
            f"/api/memberships/{membership['id']}",
            headers=auth_headers,
            json={"plan_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Plan not found"


class TestMembershipRenewal:
    """Test membership renewal."""

    def test_renew_membership(self, client, auth_headers, sample_member, sample_plan):
        """Test renewing a membership."""
        # Create first
        create_resp = client.post(
            "/api/memberships",
            headers=auth_headers,
            json={
                "member_id": str(sample_member.id),
                "plan_id": str(sample_plan.id),
                "type": "monthly",
                "start_date": str(date.today() - timedelta(days=60)),
                "end_date": str(date.today() - timedelta(days=30)),
            },
        )
        assert create_resp.status_code == 201
        membership_id = create_resp.json()["id"]

        # Renew
        renew_resp = client.post(
            f"/api/memberships/{membership_id}/renew?extend_days=30",
            headers=auth_headers,
        )
        assert renew_resp.status_code == 200
        data = renew_resp.json()
        assert data["status"] == "active"
        assert date.fromisoformat(data["end_date"]) >= date.today() + timedelta(days=29)


class TestRenewalInvalidation:
    """renew_membership must notify the CV service post-commit only —
    never on a failed/rolled-back write (3-path invalidation contract)."""

    def test_renew_triggers_post_commit_invalidation(
        self, client, auth_headers, sample_member, sample_plan, monkeypatch
    ):
        mock_notify = AsyncMock()
        monkeypatch.setattr(memberships_module, "notify_cv_invalidation", mock_notify)

        create_resp = client.post(
            "/api/memberships",
            headers=auth_headers,
            json={
                "member_id": str(sample_member.id),
                "plan_id": str(sample_plan.id),
                "type": "monthly",
                "start_date": str(date.today() - timedelta(days=60)),
                "end_date": str(date.today() - timedelta(days=30)),
            },
        )
        membership_id = create_resp.json()["id"]

        renew_resp = client.post(
            f"/api/memberships/{membership_id}/renew?extend_days=30",
            headers=auth_headers,
        )
        assert renew_resp.status_code == 200
        mock_notify.assert_awaited_once_with(str(sample_member.id))

    def test_renew_not_found_does_not_invalidate(
        self, client, auth_headers, monkeypatch
    ):
        mock_notify = AsyncMock()
        monkeypatch.setattr(memberships_module, "notify_cv_invalidation", mock_notify)

        resp = client.post(
            f"/api/memberships/{uuid.uuid4()}/renew", headers=auth_headers
        )
        assert resp.status_code == 404
        mock_notify.assert_not_awaited()
