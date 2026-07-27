"""Tests for users API endpoints."""

import pytest


def test_list_users_unauthenticated(client):
    response = client.get("/api/users")
    assert response.status_code == 401


def test_list_users_authenticated(auth_client):
    response = auth_client.get("/api/users")
    assert response.status_code == 200
    data = response.json()
    assert "users" in data


def test_get_me_authenticated(auth_client):
    response = auth_client.get("/api/auth/me")
    assert response.status_code == 200
