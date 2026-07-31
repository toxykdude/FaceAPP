"""SSRF guard tests for camera-start (net_guard + /cameras/start endpoint).

Pure config/httpx — runs in the cv_service CI job (no Redis needed).
"""

import socket
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from core.net_guard import assert_safe_rtsp


class TestAssertSafeRtsp:
    """assert_safe_rtsp must raise on private/loopback/unsafe targets."""

    def test_private_ipv4_rejected(self):
        with pytest.raises(ValueError, match="non-public"):
            assert_safe_rtsp("rtsp://192.168.1.10:554/stream")

    def test_private_ipv4_with_credentials_rejected(self):
        with pytest.raises(ValueError, match="non-public"):
            assert_safe_rtsp("rtsp://user:pass@10.0.0.1:554/stream")

    def test_loopback_rejected(self):
        for url in (
            "rtsp://127.0.0.1:554/stream",
            "rtsp://localhost:554/stream",
            "rtsp://0.0.0.0:554/stream",
            "rtsp://[::1]:554/stream",
        ):
            with pytest.raises(ValueError):
                assert_safe_rtsp(url)

    def test_link_local_rejected(self):
        with pytest.raises(ValueError, match="non-public"):
            assert_safe_rtsp("http://169.254.169.254/latest/meta-data/")

    def test_hostname_resolving_to_private_ip_rejected(self, monkeypatch):
        """DNS resolution must be checked, not just the literal hostname."""

        def fake_getaddrinfo(host, *args, **kwargs):
            if host == "camera.internal":
                return [
                    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 0))
                ]
            raise socket.gaierror("nodename nor servname provided")

        monkeypatch.setattr("core.net_guard.socket.getaddrinfo", fake_getaddrinfo)
        with pytest.raises(ValueError, match="non-public"):
            assert_safe_rtsp("rtsp://camera.internal:554/stream")

    def test_unresolvable_hostname_rejected(self):
        with pytest.raises(ValueError, match="resolve"):
            assert_safe_rtsp("rtsp://no-such-host.invalid/stream")

    def test_public_hostname_allowed(self):
        assert assert_safe_rtsp("rtsp://example.com:554/stream") == (
            "rtsp://example.com:554/stream"
        )

    def test_public_ip_allowed(self):
        assert assert_safe_rtsp("rtsp://8.8.8.8:554/stream") == "rtsp://8.8.8.8:554/stream"

    def test_local_sources_allowed(self):
        assert assert_safe_rtsp("/dev/video0") == "/dev/video0"
        assert assert_safe_rtsp("browser:camera-1") == "browser:camera-1"
        assert assert_safe_rtsp("client:camera-1") == "client:camera-1"

    def test_bad_scheme_rejected(self):
        with pytest.raises(ValueError, match="URL must start with"):
            assert_safe_rtsp("ftp://example.com/stream")

    def test_empty_rejected(self):
        with pytest.raises(ValueError):
            assert_safe_rtsp("")


class TestCameraStartEndpointSSRF:
    """The /cameras/start endpoint must abort with HTTP 400 on unsafe URLs."""

    def _post(self, monkeypatch, url):
        import main as cv_main

        monkeypatch.setattr(cv_main.settings, "API_KEY", "ssrf-test-key")
        started = AsyncMock()
        monkeypatch.setattr(cv_main.service, "start_camera", started)
        client = TestClient(cv_main.app)
        return client.post(
            "/cameras/start",
            json={"camera_id": "cam-1", "rtsp_url": url, "fps": 5},
            headers={"X-API-Key": "ssrf-test-key"},
        ), started

    def test_private_ip_rejected_with_400(self, monkeypatch):
        import main as cv_main

        resp, started = self._post(
            monkeypatch, "rtsp://user:pass@192.168.1.10:554/stream"
        )
        assert resp.status_code == 400
        started.assert_not_awaited()
        # The 400 detail must not leak the credentials either.
        assert "user:pass" not in resp.json()["detail"]

    def test_loopback_rejected_with_400(self, monkeypatch):
        import main as cv_main

        resp, started = self._post(monkeypatch, "rtsp://localhost:554/stream")
        assert resp.status_code == 400
        started.assert_not_awaited()

    def test_unresolvable_hostname_rejected_with_400(self, monkeypatch):
        import main as cv_main

        resp, started = self._post(
            monkeypatch, "rtsp://no-such-host.invalid:554/stream"
        )
        assert resp.status_code == 400
        started.assert_not_awaited()

    def test_local_device_accepted(self, monkeypatch):
        import main as cv_main

        resp, started = self._post(monkeypatch, "/dev/video0")
        # The endpoint proceeds past the guard; start_camera runs (and may
        # raise for its own reasons) — assert the guard did not block it.
        started.assert_awaited_once_with("cam-1", "/dev/video0", 5)
