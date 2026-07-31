"""Tests for authentication endpoints."""

import os

import pytest

from core.rate_limiter import real_client_ip
from starlette.requests import Request


def _build_request(headers=None, client_host="1.2.3.4"):
    """Build a minimal Starlette Request for real_client_ip unit tests."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [
            (k.lower().encode("utf-8"), v.encode("utf-8"))
            for k, v in (headers or {}).items()
        ],
        "client": (client_host, 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "root_path": "",
        "http_version": "1.1",
    }
    return Request(scope)


class TestLogin:
    """Test login endpoint."""

    def test_login_success(self, client, admin_user):
        """Test successful login with valid credentials."""
        # ADMIN_PASSWORD is set by CI (ci-admin-password); default is admin123
        # for local dev. Read from env so the test works in both contexts.
        password = os.getenv("ADMIN_PASSWORD", "admin123")
        response = client.post(
            "/api/auth/login", json={"username": "admin", "password": password}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "user" in data

    def test_login_wrong_password(self, client, admin_user):
        """Test login with wrong password."""
        response = client.post(
            "/api/auth/login", json={"username": "admin", "password": "wrongpassword"}
        )
        assert response.status_code == 401

    def test_login_nonexistent_user(self, client):
        """Test login with non-existent user."""
        response = client.post(
            "/api/auth/login", json={"username": "nonexistent", "password": "whatever"}
        )
        assert response.status_code == 401

    def test_login_missing_fields(self, client):
        """Test login with missing fields."""
        response = client.post("/api/auth/login", json={"username": "admin"})
        assert response.status_code == 422


class TestLoginTimingHardening:
    """WS-9 (CWE-208/307): unknown-username logins must cost a real bcrypt
    verify so response timing cannot enumerate usernames."""

    def test_unknown_username_verifies_against_dummy_hash(self, client, monkeypatch):
        """The not-found path must call verify_password with the dummy hash."""
        import api.auth as auth_module
        from core.security import DUMMY_PASSWORD_HASH

        calls = []

        def recording_verify(password, hashed):
            calls.append((password, hashed))
            return False

        monkeypatch.setattr(auth_module, "verify_password", recording_verify)

        resp = client.post(
            "/api/auth/login",
            json={"username": "nonexistent-user-xyz", "password": "whatever"},
        )
        assert resp.status_code == 401
        # Exactly one verify against the DUMMY hash (the known-user path is
        # never reached for an unknown username).
        assert len(calls) == 1
        assert calls[0][0] == "whatever"
        assert calls[0][1] == DUMMY_PASSWORD_HASH


class TestRealClientIp:
    """Unit tests for the rate-limiter real-client-IP key function (WS-9)."""

    def test_cf_connecting_ip_wins(self):
        """CF-Connecting-IP (set by Cloudflare) takes precedence."""
        req = _build_request(
            headers={
                "CF-Connecting-IP": "203.0.113.9",
                "X-Forwarded-For": "10.0.0.1, 203.0.113.9",
            }
        )
        assert real_client_ip(req) == "203.0.113.9"

    def test_last_xff_hop_when_no_cf_header(self):
        """Without CF-Connecting-IP, the LAST X-Forwarded-For hop is the real
        client (Nginx appends it last)."""
        req = _build_request(
            headers={"X-Forwarded-For": "10.0.0.1, 10.0.0.2, 203.0.113.9 "}
        )
        assert real_client_ip(req) == "203.0.113.9"

    def test_client_host_when_no_proxy_headers(self):
        """Direct connections fall back to request.client.host."""
        req = _build_request(client_host="198.51.100.7")
        assert real_client_ip(req) == "198.51.100.7"


class TestAuthMe:
    """Test current user endpoint."""

    def test_get_me_authenticated(self, client, auth_headers, admin_user):
        """Test getting current user info with valid token."""
        response = client.get("/api/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "admin"

    def test_get_me_unauthenticated(self, client):
        """Test getting current user info without token."""
        response = client.get("/api/auth/me")
        assert response.status_code == 401


class TestHealth:
    """Test health endpoints."""

    def test_basic_health(self, client):
        """Test basic health check."""
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
