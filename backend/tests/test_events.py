"""Tests for events API endpoints."""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


def test_list_events_unauthenticated(client):
    """Unauthenticated request should return 401."""
    response = client.get("/api/events")
    assert response.status_code == 401


def test_create_event_unauthenticated(client):
    """Unauthenticated event creation should return 401."""
    response = client.post("/api/events", json={
        "camera_id": "test",
        "member_id": None,
        "confidence_score": None,
        "access_granted": True,
    })
    assert response.status_code == 401


def test_list_events_authenticated(auth_client):
    """Authenticated request should return events list."""
    response = auth_client.get("/api/events")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "events" in data


def test_get_today_recognized_authenticated(auth_client):
    """Today recognized endpoint should return data."""
    response = auth_client.get("/api/events/today-recognized")
    assert response.status_code == 200
    data = response.json()
    assert "recognized" in data


def test_get_event_stats_authenticated(auth_client):
    """Stats endpoint should return summary."""
    response = auth_client.get("/api/events/stats/summary")
    assert response.status_code == 200


def test_get_event_not_found(auth_client):
    """Non-existent event should return 404."""
    response = auth_client.get("/api/events/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
