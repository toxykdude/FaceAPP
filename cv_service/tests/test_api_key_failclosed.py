"""
Fail-closed behavior of verify_api_key (S2).

An unconfigured API_KEY must reject every request with 503 instead of silently
allowing it. Drives the real root endpoint, which is guarded by verify_api_key
and needs no database.

(One negative + one positive per the scan's auth contract: the empty-key 503 is
the negative; the correct-header 200 is the positive.)
"""

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client():
    # Without `with`, the ASGI lifespan (service.startup -> template sync /
    # camera reconcile) never fires, so no backend/Redis calls are made.
    return TestClient(main.app)


def test_unconfigured_api_key_rejects_with_503(client, monkeypatch):
    monkeypatch.setattr(main.settings, "API_KEY", "")
    resp = client.get("/")
    assert resp.status_code == 503


def test_configured_api_key_without_header_is_401(client, monkeypatch):
    monkeypatch.setattr(main.settings, "API_KEY", "real-cv-api-key-1234567890")
    resp = client.get("/")
    assert resp.status_code == 401


def test_configured_api_key_with_wrong_header_is_401(client, monkeypatch):
    monkeypatch.setattr(main.settings, "API_KEY", "real-cv-api-key-1234567890")
    resp = client.get("/", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


def test_correct_api_key_is_allowed(client, monkeypatch):
    key = "real-cv-api-key-1234567890"
    monkeypatch.setattr(main.settings, "API_KEY", key)
    resp = client.get("/", headers={"X-API-Key": key})
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"
