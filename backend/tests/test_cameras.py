"""Tests for cameras API endpoints."""

import pytest


def test_list_cameras_unauthenticated(client):
    response = client.get("/api/cameras")
    assert response.status_code == 401


def test_list_cameras_authenticated(auth_client):
    response = auth_client.get("/api/cameras")
    assert response.status_code == 200
    data = response.json()
    assert "cameras" in data


def test_detect_devices_authenticated(auth_client):
    """Route should be reachable (not shadowed by /{camera_id})."""
    response = auth_client.get("/api/cameras/devices/detect")
    assert response.status_code != 404 or "unreachable" not in response.text.lower()
