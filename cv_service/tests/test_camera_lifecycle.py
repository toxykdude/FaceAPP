from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from main import CVService, video_feed


@pytest.mark.asyncio
async def test_requested_configured_camera_is_started_before_streaming(monkeypatch):
    camera_id = "ad0bcb04-14eb-4f78-80fa-59374b768b8c"
    processor = SimpleNamespace(rtsp_url="rtsp://camera/stream", fps=5)
    fake_service = SimpleNamespace(
        processors={},
        _ws_frames={},
        _auto_start_cameras=AsyncMock(),
    )

    async def start_requested(requested_camera_id):
        assert requested_camera_id == camera_id
        fake_service.processors[camera_id] = processor

    fake_service._auto_start_cameras.side_effect = start_requested
    monkeypatch.setattr("main.service", fake_service)

    response = await video_feed(camera_id, None)

    fake_service._auto_start_cameras.assert_awaited_once_with(camera_id)
    assert response.media_type == "multipart/x-mixed-replace; boundary=frame"


@pytest.mark.asyncio
async def test_camera_reconcile_starts_new_and_stops_removed_config():
    service = CVService.__new__(CVService)
    removed = Mock()
    removed.rtsp_url = "rtsp://old/stream"
    removed.fps = 5
    service.processors = {"removed-camera": removed}
    service.api_client = SimpleNamespace(
        get_cameras=AsyncMock(
            return_value=[
                {
                    "id": "new-camera",
                    "name": "Entrance",
                    "rtsp_url": "rtsp://camera/stream",
                    "fps": 7,
                }
            ]
        )
    )
    service.stop_camera = Mock(side_effect=lambda camera_id: service.processors.pop(camera_id))
    service.start_camera = AsyncMock()

    await service._reconcile_cameras()

    service.stop_camera.assert_called_once_with("removed-camera")
    service.start_camera.assert_awaited_once_with(
        camera_id="new-camera", rtsp_url="rtsp://camera/stream", fps=7
    )


def test_failed_connect_health_hides_rtsp_credentials(monkeypatch):
    """A failed connection must not leak the RTSP URL or its credentials.

    rtsp_failure_url_health_exposure: the full URL (which may embed
    user:pass) used to land verbatim in last_error and get exposed via
    get_health() to the authenticated /health endpoint.

    The processor is built with __new__ (no FaceNet model construction,
    which downloads weights) and only the fields _connect_stream and
    get_health touch are seeded.
    """
    from stream.rtsp_processor import RTSPStreamProcessor

    url = "rtsp://user:pass@10.0.0.1:554/stream"
    processor = RTSPStreamProcessor.__new__(RTSPStreamProcessor)
    processor.camera_id = "cam-1"
    processor.rtsp_url = url
    processor.fps = 5
    processor.frame_interval = 1.0 / 5
    processor.is_running = False
    processor.connected = False
    processor.last_frame_time = 0
    processor.total_frames_processed = 0
    processor.total_faces_detected = 0
    processor.last_error = None
    processor._frames_dropped = 0
    processor._is_http_snapshot = False
    processor._is_browser_mode = False

    class _FakeCapture:
        def isOpened(self):
            return False

        def set(self, *args, **kwargs):
            return False

        def release(self):
            pass

    monkeypatch.setattr(
        "stream.rtsp_processor.cv2.VideoCapture", lambda *a, **k: _FakeCapture()
    )

    assert processor._connect_stream() is False

    health = processor.get_health()
    assert health["last_error"] is not None
    assert "rtsp://" not in health["last_error"]
    assert "user:pass" not in health["last_error"]


def test_sanitize_rtsp_url_strips_userinfo():
    """sanitize_rtsp_url must remove user:pass but keep host and port."""
    from stream.rtsp_processor import sanitize_rtsp_url

    assert (
        sanitize_rtsp_url("rtsp://user:pass@10.0.0.1:554/stream")
        == "rtsp://10.0.0.1:554/stream"
    )
    assert (
        sanitize_rtsp_url("http://admin:s3cret@192.168.1.5/snapshot.jpg")
        == "http://192.168.1.5/snapshot.jpg"
    )
    # No userinfo — unchanged
    assert sanitize_rtsp_url("rtsp://10.0.0.1:554/stream") == "rtsp://10.0.0.1:554/stream"
    # Local sources pass through untouched
    assert sanitize_rtsp_url("/dev/video0") == "/dev/video0"
    assert sanitize_rtsp_url("browser:camera-1") == "browser:camera-1"
