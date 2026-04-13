"""Tests for membership endpoints."""
import pytest
from datetime import date, timedelta


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
