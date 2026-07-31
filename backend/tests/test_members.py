"""Tests for member CRUD endpoints."""

import uuid
import pytest


class TestMemberList:
    """Test member listing."""

    def test_list_members_authenticated(self, client, auth_headers, sample_member):
        """Test listing members with valid auth."""
        response = client.get("/api/members", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "members" in data
        assert "total" in data
        assert data["total"] >= 1

    def test_list_members_unauthenticated(self, client):
        """Test listing members without auth."""
        response = client.get("/api/members")
        assert response.status_code == 401

    def test_list_members_with_search(self, client, auth_headers, sample_member):
        """Test searching members."""
        response = client.get("/api/members?search=Test", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1


class TestMemberCreate:
    """Test member creation."""

    def test_create_member_success(self, client, auth_headers):
        """Test creating a member with valid data."""
        unique_email = f"john.doe.{uuid.uuid4().hex[:8]}@test.com"
        response = client.post(
            "/api/members",
            headers=auth_headers,
            json={
                "first_name": "John",
                "last_name": "Doe",
                "email": unique_email,
                "phone": "555-0200",
                "consent_given": True,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["first_name"] == "John"
        assert data["last_name"] == "Doe"
        assert data["status"] == "active"

    def test_create_member_missing_required(self, client, auth_headers):
        """Test creating member with missing required fields."""
        response = client.post("/api/members", headers=auth_headers, json={})
        assert response.status_code == 422


class TestMemberPhoneUniqueness:
    """WS-9: member phone must be unique (pre-check mirrors the email check)."""

    def test_create_member_duplicate_phone_400(self, client, auth_headers):
        """Second create with an already-registered phone -> 400 (pre-check)."""
        phone = "555-4444"
        base = {
            "first_name": "Dup",
            "last_name": "Phone",
            "phone": phone,
            "consent_given": True,
        }

        resp1 = client.post(
            "/api/members",
            headers=auth_headers,
            json={**base, "email": f"dup1.{uuid.uuid4().hex[:8]}@test.com"},
        )
        assert resp1.status_code == 201, resp1.text

        resp2 = client.post(
            "/api/members",
            headers=auth_headers,
            json={**base, "email": f"dup2.{uuid.uuid4().hex[:8]}@test.com"},
        )
        assert resp2.status_code == 400, resp2.text
        assert resp2.json()["detail"] == "Phone already registered"


class TestMemberGetUpdateDelete:
    """Test member get, update, delete."""

    def test_get_member(self, client, auth_headers, sample_member):
        """Test getting a specific member."""
        response = client.get(f"/api/members/{sample_member.id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["first_name"] == "Test"

    def test_get_member_not_found(self, client, auth_headers):
        """Test getting non-existent member."""
        response = client.get(
            "/api/members/00000000-0000-0000-0000-000000000000", headers=auth_headers
        )
        assert response.status_code == 404

    def test_update_member(self, client, auth_headers, sample_member):
        """Test updating a member."""
        response = client.put(
            f"/api/members/{sample_member.id}",
            headers=auth_headers,
            json={"first_name": "Updated"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["first_name"] == "Updated"

    def test_delete_member(self, client, auth_headers, sample_member):
        """Test deleting a member."""
        response = client.delete(
            f"/api/members/{sample_member.id}", headers=auth_headers
        )
        assert response.status_code == 204

        # Verify deleted
        response = client.get(f"/api/members/{sample_member.id}", headers=auth_headers)
        assert response.status_code == 404
