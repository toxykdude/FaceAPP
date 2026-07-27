"""
Tests for the shared CV cache-invalidation notifier (services/cv_notify.py).

Extracted from the inline `notify_cv_invalidation` previously defined only
in `api/members.py` (lines 31-38) so `memberships.py` and `portal.py` can
reuse the exact same POST /invalidate/{id} + X-API-Key contract.
"""
import pytest

from services.cv_notify import notify_cv_invalidation
from core.config import settings


class _FakeResponse:
    status_code = 200


class _FakeAsyncClient:
    """Captures the call args instead of hitting a real network."""

    def __init__(self, captured, *args, **kwargs):
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, headers=None):
        self._captured["url"] = url
        self._captured["headers"] = headers
        return _FakeResponse()


def _patch_async_client(monkeypatch, captured):
    import services.cv_notify as cv_notify_module

    def factory(*args, **kwargs):
        return _FakeAsyncClient(captured, *args, **kwargs)

    monkeypatch.setattr(cv_notify_module.httpx, "AsyncClient", factory)


class TestNotifyCvInvalidation:
    """notify_cv_invalidation(id) POSTs {CV_SERVICE_URL}/invalidate/{id}
    with X-API-Key: settings.CV_API_KEY."""

    @pytest.mark.asyncio
    async def test_posts_to_invalidate_endpoint_with_api_key(self, monkeypatch):
        monkeypatch.setattr(settings, "CV_API_KEY", "secret-key-1")
        monkeypatch.setattr(settings, "CV_SERVICE_URL", "http://cv-service:9001")
        captured = {}
        _patch_async_client(monkeypatch, captured)

        await notify_cv_invalidation("member-abc-123")

        assert captured["url"] == "http://cv-service:9001/invalidate/member-abc-123"
        assert captured["headers"]["X-API-Key"] == "secret-key-1"

    @pytest.mark.asyncio
    async def test_different_member_and_key_produce_different_call(self, monkeypatch):
        """Triangulation: a different member_id and API key change both the
        posted URL and header — proving no hardcoded Fake-It values."""
        monkeypatch.setattr(settings, "CV_API_KEY", "another-key-999")
        monkeypatch.setattr(settings, "CV_SERVICE_URL", "http://cv.internal")
        captured = {}
        _patch_async_client(monkeypatch, captured)

        await notify_cv_invalidation("member-xyz-999")

        assert captured["url"] == "http://cv.internal/invalidate/member-xyz-999"
        assert captured["headers"]["X-API-Key"] == "another-key-999"

    @pytest.mark.asyncio
    async def test_no_api_key_header_when_cv_api_key_unset(self, monkeypatch):
        """Edge case: when CV_API_KEY is empty, no X-API-Key header is sent
        (matches the original inline behavior at members.py:35)."""
        monkeypatch.setattr(settings, "CV_API_KEY", "")
        monkeypatch.setattr(settings, "CV_SERVICE_URL", "http://cv.internal")
        captured = {}
        _patch_async_client(monkeypatch, captured)

        await notify_cv_invalidation("member-no-key")

        assert captured["headers"] == {}
