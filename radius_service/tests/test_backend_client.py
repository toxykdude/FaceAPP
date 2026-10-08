"""
BackendClient tests: URL join, header injection, error mapping.

Uses a stubbed httpx transport (no network). The contract that matters most:
authorize() must RAISE on any failure so the RADIUS layer fails closed, and
send_accounting() must never raise.
"""

import sys
import json
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend_client import (  # noqa: E402
    BackendAuthError,
    BackendClient,
    BackendError,
)


def client_with(handler, secret="unit-secret"):
    transport = httpx.MockTransport(handler)
    client = BackendClient(
        base_url="http://backend.test/api", secret=secret, timeout=2.0
    )
    client._client._transport = transport
    return client


def test_authorize_posts_internal_secret_and_body():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["secret"] = request.headers.get("X-Internal-Secret")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"allowed": True, "reason": None})

    client = client_with(handler)
    decision = client.authorize("123456789", client_mac="AA:BB", nas_ip="10.0.0.1")

    assert decision["allowed"] is True
    assert seen["url"] == "http://backend.test/api/wifi/authorize"
    assert seen["secret"] == "unit-secret"
    assert seen["body"]["document"] == "123456789"
    assert seen["body"]["client_mac"] == "AA:BB"


def test_authorize_raises_on_auth_failure():
    client = client_with(lambda r: httpx.Response(401, json={}))
    with pytest.raises(BackendAuthError):
        client.authorize("123")
    client = client_with(lambda r: httpx.Response(503, json={}))
    with pytest.raises(BackendAuthError):
        client.authorize("123")


def test_authorize_raises_on_server_error():
    client = client_with(lambda r: httpx.Response(500, json={}))
    with pytest.raises(BackendError):
        client.authorize("123")


def test_authorize_raises_on_transport_error():
    def handler(request):
        raise httpx.ConnectError("boom")

    client = client_with(handler)
    with pytest.raises(BackendError):
        client.authorize("123")


def test_accounting_returns_true_on_200():
    client = client_with(lambda r: httpx.Response(200, json={"recorded": True}))
    assert client.send_accounting({"status": "start"}) is True


def test_accounting_returns_false_never_raises():
    def handler(request):
        raise httpx.ConnectError("boom")

    client = client_with(handler)
    assert client.send_accounting({"status": "stop"}) is False
    client = client_with(lambda r: httpx.Response(500, json={}))
    assert client.send_accounting({"status": "stop"}) is False
