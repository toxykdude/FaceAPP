"""Tests for member CRUD endpoints."""

import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from api.members import create_member
from schemas.member import MemberCreate


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


class TestMemberContactPhone:
    """Phone is nullable, non-unique member contact data."""

    def test_create_members_with_duplicate_phone(self, client, auth_headers):
        phone = "555-4444"
        responses = [
            client.post(
                "/api/members",
                headers=auth_headers,
                json={
                    "first_name": f"Contact{index}",
                    "last_name": "Member",
                    "email": f"contact{index}.{uuid.uuid4().hex[:8]}@test.com",
                    "phone": phone,
                },
            )
            for index in range(2)
        ]

        assert [response.status_code for response in responses] == [201, 201]
        assert responses[0].json()["id"] != responses[1].json()["id"]
        assert {response.json()["phone"] for response in responses} == {phone}

    def test_update_member_to_existing_phone(self, client, auth_headers, sample_member):
        created = client.post(
            "/api/members",
            headers=auth_headers,
            json={
                "first_name": "Other",
                "last_name": "Member",
                "email": f"other.{uuid.uuid4().hex[:8]}@test.com",
                "phone": "555-5555",
            },
        )
        assert created.status_code == 201, created.text

        response = client.put(
            f"/api/members/{created.json()['id']}",
            headers=auth_headers,
            json={"phone": sample_member.phone},
        )

        assert response.status_code == 200, response.text
        assert response.json()["phone"] == sample_member.phone

    def test_duplicate_email_stays_an_accurate_safe_error(self, client, auth_headers):
        email = f"duplicate.{uuid.uuid4().hex[:8]}@test.com"
        base = {"first_name": "Email", "last_name": "Member", "email": email}
        first = client.post("/api/members", headers=auth_headers, json=base)
        second = client.post("/api/members", headers=auth_headers, json=base)

        assert first.status_code == 201, first.text
        assert second.status_code == 400
        assert second.json() == {"detail": "Email already registered"}

    def test_unknown_integrity_error_is_generic_and_rolls_back(self):
        original = Exception("private database detail")
        setattr(
            original,
            "diag",
            SimpleNamespace(constraint_name="unexpected_constraint"),
        )
        db = Mock()
        db.flush.side_effect = IntegrityError("private statement", {}, original)

        with pytest.raises(HTTPException) as caught:
            create_member(
                MemberCreate(first_name="Conflict", last_name="Member"),
                db=db,
                current_user=Mock(id=uuid.uuid4(), username="tester"),
            )

        assert caught.value.status_code == 409
        assert caught.value.detail == "Member conflicts with existing data"
        assert "phone" not in str(caught.value.detail).lower()
        assert "private" not in str(caught.value.detail).lower()
        db.rollback.assert_called_once_with()


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
