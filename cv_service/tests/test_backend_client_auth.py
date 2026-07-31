"""
Security tests for BackendAPIClient authentication and error propagation.

These tests run WITHOUT torch/facenet: BackendAPIClient is imported directly
from api.backend_client (not via cv_service.main), and config.py only depends
on pydantic-settings. The real httpx.AsyncClient is used with an injected
httpx.MockTransport so that the X-Internal-Secret header the client
configures is actually applied to each request and can be inspected.
"""

import sys
from pathlib import Path

import httpx
import pytest
from loguru import logger

# Make cv_service/ importable (so `from config import settings` resolves)
# without pulling in cv_service.main (which imports torch-dependent modules).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from api.backend_client import (  # noqa: E402
    BackendAPIClient,
    _AUTH_CONFIG_FAILURE_STATUSES,
)

TEST_SECRET = "test-internal-secret"
# Save the real AsyncClient before patching it in _build_client.
_REAL_ASYNC_CLIENT = httpx.AsyncClient


@pytest.fixture
def loguru_errors():
    """Capture loguru records at ERROR+ into a list of formatted strings.

    Used to assert that transient/non-auth errors are LOGGED even though
    the methods now return an empty value instead of raising.
    """
    messages = []

    def sink(message):
        messages.append(str(message))

    handle_id = logger.add(sink, level="ERROR", format="{message}")
    try:
        yield messages
    finally:
        logger.remove(handle_id)


def _assert_error_logged(messages, needle):
    """Assert at least one captured ERROR message contains ``needle``."""
    assert any(
        needle in msg for msg in messages
    ), f"expected an ERROR log containing {needle!r}; got {messages!r}"


def _build_client(handler, monkeypatch):
    """Build a BackendAPIClient whose inner client uses a MockTransport.

    Patches httpx.AsyncClient inside backend_client so the real client is
    constructed with the real headers the production code configures, plus
    an injected transport that routes through ``handler``. Returns
    ``(client, handler)`` where ``handler.last_request`` is the most recent
    httpx.Request seen (so tests can inspect outbound headers).
    """
    monkeypatch.setattr(config.settings, "INTERNAL_API_SECRET", TEST_SECRET)

    def fake_async_client(*args, **kwargs):
        return _REAL_ASYNC_CLIENT(
            *args, transport=httpx.MockTransport(handler), **kwargs
        )

    monkeypatch.setattr(
        "api.backend_client.httpx.AsyncClient",
        fake_async_client,
    )
    client = BackendAPIClient()
    return client, handler


def _make_handler(status_code, json_body=None):
    """Return a MockTransport handler capturing the last request."""

    def handler(request):
        handler.last_request = request
        return httpx.Response(status_code, json=json_body or {})

    handler.last_request = None
    return handler


def _assert_secret_header(handler):
    """Assert the captured outbound request carried the shared secret."""
    assert handler.last_request is not None, "no request was captured"
    assert (
        handler.last_request.headers["X-Internal-Secret"] == TEST_SECRET
    ), "request did not carry the X-Internal-Secret header"


# --- __init__ ------------------------------------------------------------


def test_init_requires_secret(monkeypatch):
    """Empty INTERNAL_API_SECRET must fail fast at construction."""
    monkeypatch.setattr(config.settings, "INTERNAL_API_SECRET", "")
    with pytest.raises(RuntimeError, match="INTERNAL_API_SECRET"):
        BackendAPIClient()


def test_init_with_secret_attaches_header(monkeypatch):
    """A configured secret must be attached as a client header.

    The wire-level header is asserted in every async test below via
    _assert_secret_header; here we confirm construction wired it in.
    """
    handler = _make_handler(200, {"templates": []})
    client, handler = _build_client(handler, monkeypatch)
    assert client._headers["X-Internal-Secret"] == TEST_SECRET


def test_init_refuses_cleartext_backend_when_required(monkeypatch):
    """REQUIRE_PROD_SECRETS must refuse a cleartext http:// backend URL.

    The internal secret and biometric payloads travel over this channel;
    in production-strict mode plaintext HTTP is a hard config error.
    """
    monkeypatch.setattr(config.settings, "INTERNAL_API_SECRET", TEST_SECRET)
    monkeypatch.setattr(config.settings, "REQUIRE_PROD_SECRETS", True)
    monkeypatch.setattr(
        config.settings, "BACKEND_API_URL", "http://backend:8000/api"
    )
    with pytest.raises(RuntimeError, match="REQUIRE_PROD_SECRETS"):
        BackendAPIClient()


def test_init_allows_cleartext_backend_in_dev_mode(monkeypatch):
    """Without REQUIRE_PROD_SECRETS the dev http:// URL stays usable."""
    monkeypatch.setattr(config.settings, "INTERNAL_API_SECRET", TEST_SECRET)
    monkeypatch.setattr(config.settings, "REQUIRE_PROD_SECRETS", False)
    monkeypatch.setattr(
        config.settings, "BACKEND_API_URL", "http://backend:8000/api"
    )
    client = BackendAPIClient()
    assert client.base_url == "http://backend:8000/api"


def test_init_allows_https_backend_when_required(monkeypatch):
    """https:// URLs pass the strict-mode guard."""
    monkeypatch.setattr(config.settings, "INTERNAL_API_SECRET", TEST_SECRET)
    monkeypatch.setattr(config.settings, "REQUIRE_PROD_SECRETS", True)
    monkeypatch.setattr(
        config.settings, "BACKEND_API_URL", "https://api.facegym.example/api"
    )
    client = BackendAPIClient()
    assert client.base_url == "https://api.facegym.example/api"


# --- sync_templates ------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_templates_success(monkeypatch):
    handler = _make_handler(
        200, {"templates": [{"member_id": "m1"}, {"member_id": "m2"}]}
    )
    client, handler = _build_client(handler, monkeypatch)
    result = await client.sync_templates()
    assert result == [{"member_id": "m1"}, {"member_id": "m2"}]
    _assert_secret_header(handler)


@pytest.mark.parametrize("status", sorted(_AUTH_CONFIG_FAILURE_STATUSES))
@pytest.mark.asyncio
async def test_sync_templates_auth_failure_raises(monkeypatch, status):
    handler = _make_handler(status)
    client, handler = _build_client(handler, monkeypatch)
    with pytest.raises(RuntimeError):
        await client.sync_templates()
    _assert_secret_header(handler)


@pytest.mark.asyncio
async def test_sync_templates_500_returns_empty(monkeypatch, loguru_errors):
    """Non-auth HTTP errors are loud but non-fatal: return [] + log ERROR."""
    handler = _make_handler(500)
    client, handler = _build_client(handler, monkeypatch)
    assert await client.sync_templates() == []
    _assert_error_logged(loguru_errors, "sync_templates")


@pytest.mark.asyncio
async def test_sync_templates_network_error_returns_empty(
    monkeypatch,
    loguru_errors,
):
    def handler(request):
        handler.last_request = request
        raise httpx.ConnectError("connection refused")

    handler.last_request = None
    client, handler = _build_client(handler, monkeypatch)
    assert await client.sync_templates() == []
    _assert_secret_header(handler)
    _assert_error_logged(loguru_errors, "sync_templates")


# --- get_member ----------------------------------------------------------


@pytest.mark.asyncio
async def test_get_member_success(monkeypatch):
    handler = _make_handler(200, {"id": "m1", "status": "active"})
    client, handler = _build_client(handler, monkeypatch)
    result = await client.get_member("m1")
    assert result == {"id": "m1", "status": "active"}
    _assert_secret_header(handler)


@pytest.mark.asyncio
async def test_get_member_404_returns_none(monkeypatch):
    handler = _make_handler(404)
    client, handler = _build_client(handler, monkeypatch)
    assert await client.get_member("missing") is None
    _assert_secret_header(handler)


@pytest.mark.parametrize("status", sorted(_AUTH_CONFIG_FAILURE_STATUSES))
@pytest.mark.asyncio
async def test_get_member_auth_failure_raises(monkeypatch, status):
    handler = _make_handler(status)
    client, handler = _build_client(handler, monkeypatch)
    with pytest.raises(RuntimeError):
        await client.get_member("m1")
    _assert_secret_header(handler)


@pytest.mark.asyncio
async def test_get_member_network_error_returns_none(
    monkeypatch,
    loguru_errors,
):
    """Transient backend errors must not crash the access-validator loop.

    get_member runs unguarded on every recognition; on a network blip it
    returns None (validator denies access — fail-safe) instead of raising.
    """

    def handler(request):
        handler.last_request = request
        raise httpx.ConnectError("connection refused")

    handler.last_request = None
    client, handler = _build_client(handler, monkeypatch)
    assert await client.get_member("m1") is None
    _assert_secret_header(handler)
    _assert_error_logged(loguru_errors, "get_member")


# --- get_active_membership ----------------------------------------------


@pytest.mark.asyncio
async def test_get_active_membership_active(monkeypatch):
    handler = _make_handler(
        200, {"has_active": True, "membership": {"status": "active"}}
    )
    client, handler = _build_client(handler, monkeypatch)
    result = await client.get_active_membership("m1")
    assert result == {"status": "active"}
    _assert_secret_header(handler)


@pytest.mark.asyncio
async def test_get_active_membership_inactive(monkeypatch):
    handler = _make_handler(200, {"has_active": False, "membership": None})
    client, handler = _build_client(handler, monkeypatch)
    assert await client.get_active_membership("m1") is None


@pytest.mark.asyncio
async def test_get_active_membership_404_returns_none(monkeypatch):
    handler = _make_handler(404)
    client, handler = _build_client(handler, monkeypatch)
    assert await client.get_active_membership("m1") is None


@pytest.mark.parametrize("status", sorted(_AUTH_CONFIG_FAILURE_STATUSES))
@pytest.mark.asyncio
async def test_get_active_membership_auth_failure_raises(monkeypatch, status):
    handler = _make_handler(status)
    client, handler = _build_client(handler, monkeypatch)
    with pytest.raises(RuntimeError):
        await client.get_active_membership("m1")
    _assert_secret_header(handler)


# --- get_cameras ---------------------------------------------------------


@pytest.mark.asyncio
async def test_get_cameras_success(monkeypatch):
    handler = _make_handler(
        200,
        {"cameras": [{"id": "c1", "rtsp_url": "rtsp://x"}]},
    )
    client, handler = _build_client(handler, monkeypatch)
    result = await client.get_cameras()
    assert result == [{"id": "c1", "rtsp_url": "rtsp://x"}]
    _assert_secret_header(handler)


@pytest.mark.parametrize("status", sorted(_AUTH_CONFIG_FAILURE_STATUSES))
@pytest.mark.asyncio
async def test_get_cameras_auth_failure_raises(monkeypatch, status):
    handler = _make_handler(status)
    client, handler = _build_client(handler, monkeypatch)
    with pytest.raises(RuntimeError):
        await client.get_cameras()
    _assert_secret_header(handler)


# --- create_access_event -------------------------------------------------


@pytest.mark.asyncio
async def test_create_access_event_success(monkeypatch):
    handler = _make_handler(200, {"id": 1, "access_granted": True})
    client, handler = _build_client(handler, monkeypatch)
    result = await client.create_access_event(
        camera_id="c1",
        member_id="m1",
        confidence_score=0.99,
        access_granted=True,
    )
    assert result == {"id": 1, "access_granted": True}
    _assert_secret_header(handler)
    # Verify the event payload was posted.
    assert handler.last_request.method == "POST"
    assert handler.last_request.url.path.endswith("/events")


@pytest.mark.parametrize("status", sorted(_AUTH_CONFIG_FAILURE_STATUSES))
@pytest.mark.asyncio
async def test_create_access_event_auth_failure_raises(monkeypatch, status):
    handler = _make_handler(status)
    client, handler = _build_client(handler, monkeypatch)
    with pytest.raises(RuntimeError):
        await client.create_access_event(
            camera_id="c1",
            member_id="m1",
            confidence_score=0.5,
            access_granted=False,
            denial_reason="no_active_membership",
        )
    _assert_secret_header(handler)


@pytest.mark.asyncio
async def test_create_access_event_500_returns_none(
    monkeypatch,
    loguru_errors,
):
    """Non-auth backend error on the audit path: log ERROR, return None."""
    handler = _make_handler(500)
    client, handler = _build_client(handler, monkeypatch)
    assert (
        await client.create_access_event(
            camera_id="c1",
            member_id="m1",
            confidence_score=0.5,
            access_granted=False,
        )
        is None
    )
    _assert_error_logged(loguru_errors, "create_access_event")
