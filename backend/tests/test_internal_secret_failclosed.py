"""
Fail-closed behavior of verify_internal_secret (S1).

An unconfigured INTERNAL_API_SECRET must reject every request with 503 instead
of silently allowing it. These tests pin a real secret onto settings and drive a
minimal endpoint guarded by the PRODUCTION dependency, exercising the exact
fail-closed logic without needing a database.

(One negative + one positive per the scan's auth contract: the empty-secret 503
is the negative; the correct-header 200 is the positive.)
"""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from api import cv_internal


@pytest.fixture
def guarded_app():
    app = FastAPI()

    @app.get("/guarded")
    def guarded(_: str = Depends(cv_internal.verify_internal_secret)):
        return {"ok": True}

    return app


@pytest.fixture
def client(guarded_app):
    return TestClient(guarded_app)


def test_unconfigured_secret_rejects_with_503(client, monkeypatch):
    monkeypatch.setattr(cv_internal.settings, "INTERNAL_API_SECRET", "")
    resp = client.get("/guarded", headers={"X-Internal-Secret": "anything"})
    assert resp.status_code == 503


def test_configured_secret_without_header_is_401(client, monkeypatch):
    monkeypatch.setattr(
        cv_internal.settings, "INTERNAL_API_SECRET", "real-internal-secret"
    )
    resp = client.get("/guarded")
    assert resp.status_code == 401


def test_configured_secret_with_wrong_header_is_401(client, monkeypatch):
    monkeypatch.setattr(
        cv_internal.settings, "INTERNAL_API_SECRET", "real-internal-secret"
    )
    resp = client.get("/guarded", headers={"X-Internal-Secret": "wrong"})
    assert resp.status_code == 401


def test_correct_header_is_allowed(client, monkeypatch):
    secret = "real-internal-secret"
    monkeypatch.setattr(cv_internal.settings, "INTERNAL_API_SECRET", secret)
    resp = client.get("/guarded", headers={"X-Internal-Secret": secret})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
