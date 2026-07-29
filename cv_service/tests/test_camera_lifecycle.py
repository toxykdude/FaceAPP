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
    assert response.media_type == "multipart/x-mixed-replace"


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
