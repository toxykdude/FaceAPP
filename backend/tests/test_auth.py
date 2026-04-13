"""Tests for authentication endpoints."""
import pytest


class TestLogin:
    """Test login endpoint."""
    
    def test_login_success(self, client, admin_user):
        """Test successful login with valid credentials."""
        response = client.post("/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "user" in data
    
    def test_login_wrong_password(self, client, admin_user):
        """Test login with wrong password."""
        response = client.post("/api/auth/login", json={
            "username": "admin",
            "password": "wrongpassword"
        })
        assert response.status_code == 401
    
    def test_login_nonexistent_user(self, client):
        """Test login with non-existent user."""
        response = client.post("/api/auth/login", json={
            "username": "nonexistent",
            "password": "whatever"
        })
        assert response.status_code == 401
    
    def test_login_missing_fields(self, client):
        """Test login with missing fields."""
        response = client.post("/api/auth/login", json={"username": "admin"})
        assert response.status_code == 422


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
        assert response.status_code == 403


class TestHealth:
    """Test health endpoints."""
    
    def test_basic_health(self, client):
        """Test basic health check."""
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
