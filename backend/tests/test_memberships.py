"""Tests for membership endpoints."""
import uuid
import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock

import api.memberships as memberships_module


class TestMembershipCreate:
    """Test membership creation."""
    
    def test_create_membership(self, client, auth_headers, sample_member):
        """Test creating a membership."""
        response = client.post("/api/memberships", headers=auth_headers, json={
            "member_id": str(sample_member.id),
            "type": "monthly",
            "start_date": str(date.today()),
            "end_date": str(date.today() + timedelta(days=30)),
            "price": 29.99
        })
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "active"
        assert data["type"] == "monthly"


class TestMembershipRenewal:
    """Test membership renewal."""
    
    def test_renew_membership(self, client, auth_headers, sample_member):
        """Test renewing a membership."""
        # Create first
        create_resp = client.post("/api/memberships", headers=auth_headers, json={
            "member_id": str(sample_member.id),
            "type": "monthly",
            "start_date": str(date.today() - timedelta(days=60)),
            "end_date": str(date.today() - timedelta(days=30)),
            "price": 29.99
        })
        assert create_resp.status_code == 201
        membership_id = create_resp.json()["id"]
        
        # Renew
        renew_resp = client.post(
            f"/api/memberships/{membership_id}/renew?extend_days=30",
            headers=auth_headers
        )
        assert renew_resp.status_code == 200
        data = renew_resp.json()
        assert data["status"] == "active"
        assert date.fromisoformat(data["end_date"]) >= date.today() + timedelta(days=29)


class TestRenewalInvalidation:
    """renew_membership must notify the CV service post-commit only —
    never on a failed/rolled-back write (3-path invalidation contract)."""

    def test_renew_triggers_post_commit_invalidation(
        self, client, auth_headers, sample_member, monkeypatch
    ):
        mock_notify = AsyncMock()
        monkeypatch.setattr(memberships_module, "notify_cv_invalidation", mock_notify)

        create_resp = client.post("/api/memberships", headers=auth_headers, json={
            "member_id": str(sample_member.id),
            "type": "monthly",
            "start_date": str(date.today() - timedelta(days=60)),
            "end_date": str(date.today() - timedelta(days=30)),
            "price": 29.99
        })
        membership_id = create_resp.json()["id"]

        renew_resp = client.post(
            f"/api/memberships/{membership_id}/renew?extend_days=30",
            headers=auth_headers
        )
        assert renew_resp.status_code == 200
        mock_notify.assert_awaited_once_with(str(sample_member.id))

    def test_renew_not_found_does_not_invalidate(self, client, auth_headers, monkeypatch):
        mock_notify = AsyncMock()
        monkeypatch.setattr(memberships_module, "notify_cv_invalidation", mock_notify)

        resp = client.post(
            f"/api/memberships/{uuid.uuid4()}/renew",
            headers=auth_headers
        )
        assert resp.status_code == 404
        mock_notify.assert_not_awaited()
