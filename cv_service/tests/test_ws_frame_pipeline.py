"""
Tests for the kiosk WebSocket frame pipeline.

The kiosk pushes browser camera frames over a WebSocket and renders whatever
comes back. Two properties matter here:

1. A recognition result must carry days_remaining so the kiosk can show an
   "expiring soon" warning.
2. A failure while processing ONE frame must not tear down the connection.
   The kiosk reports a dropped WebSocket as "Camera unavailable — check the
   connection", so a recognition-pipeline exception used to masquerade as a
   hardware/network fault the moment anyone stood in front of the camera.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from types import SimpleNamespace
from unittest.mock import AsyncMock

import cv2
import numpy as np
import pytest
from fastapi import WebSocketDisconnect

import main
from main import WsPipelineComponents, process_ws_frame, websocket_camera_feed


def _jpeg_frame():
    """A real JPEG payload so cv2.imdecode produces a usable frame."""
    image = np.zeros((64, 64, 3), dtype=np.uint8)
    ok, buffer = cv2.imencode(".jpg", image)
    assert ok
    return buffer.tobytes()


def _components(
    faces=((10, 10, 30, 30), None),
    quality=0.9,
    is_live=True,
    match=("member-1", 0.93, {"name": "Juan Cardona"}),
):
    """Pipeline components with every heavy model replaced by a stub."""
    return WsPipelineComponents(
        detector=SimpleNamespace(
            detect_faces_with_landmarks=lambda frame: [faces] if faces else [],
            align_face=lambda frame, bbox, landmarks: frame,
        ),
        quality_assessor=SimpleNamespace(
            assess_quality=lambda roi: (quality, {}),
        ),
        liveness_detector=SimpleNamespace(
            check_liveness=lambda frame, roi, bbox, landmarks=None: (is_live, {}),
        ),
        recognizer=SimpleNamespace(
            generate_embedding=lambda roi: np.zeros(512, dtype=np.float32),
        ),
        matcher=SimpleNamespace(find_match=lambda embedding: match),
    )


@pytest.fixture
def isolated_service(monkeypatch):
    """A stand-in global service so tests never touch real backends."""
    fake = SimpleNamespace(
        _ws_frames={},
        _recent_events={},
        _event_cooldown=30.0,
        validator=SimpleNamespace(
            validate_access=AsyncMock(return_value=(True, None, 12)),
        ),
        api_client=SimpleNamespace(create_access_event=AsyncMock()),
    )
    monkeypatch.setattr(main, "service", fake)
    monkeypatch.setattr(main.settings, "API_KEY", "")
    monkeypatch.setattr(main, "save_member_photo", lambda *a, **k: None)
    return fake


class _FakeWebSocket:
    """Feeds a fixed list of frames, then disconnects like a real client."""

    def __init__(self, frames):
        self._frames = list(frames)
        self.sent = []
        self.accepted = False
        self.close_code = None
        self.query_params = {}

    async def accept(self):
        self.accepted = True

    async def receive_bytes(self):
        if not self._frames:
            raise WebSocketDisconnect()
        return self._frames.pop(0)

    async def send_json(self, payload):
        self.sent.append(payload)

    async def close(self, code=None, reason=None):
        self.close_code = code


class TestProcessWsFrame:
    @pytest.mark.asyncio
    async def test_recognition_payload_carries_days_remaining(self, isolated_service):
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        isolated_service.validator.validate_access.return_value = (True, None, 4)

        payload = await process_ws_frame(
            frame, "cam-1", _components(), frame_count=1, fps=5.0
        )

        assert payload["type"] == "recognition"
        assert payload["member_name"] == "Juan Cardona"
        assert payload["access_granted"] is True
        assert payload["days_remaining"] == 4

    @pytest.mark.asyncio
    async def test_denied_payload_carries_reason_and_no_days(self, isolated_service):
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        isolated_service.validator.validate_access.return_value = (
            False,
            "expired_membership",
            None,
        )

        payload = await process_ws_frame(
            frame, "cam-1", _components(), frame_count=1, fps=5.0
        )

        assert payload["access_granted"] is False
        assert payload["denial_reason"] == "expired_membership"
        assert payload["days_remaining"] is None

    @pytest.mark.asyncio
    async def test_status_payload_when_no_face_present(self, isolated_service):
        frame = np.zeros((64, 64, 3), dtype=np.uint8)

        payload = await process_ws_frame(
            frame, "cam-1", _components(faces=None), frame_count=7, fps=5.0
        )

        assert payload == {
            "type": "status",
            "fps": 5.0,
            "frames_processed": 7,
            "faces": 0,
        }

    @pytest.mark.asyncio
    async def test_low_quality_frame_reports_nothing(self, isolated_service):
        frame = np.zeros((64, 64, 3), dtype=np.uint8)

        payload = await process_ws_frame(
            frame, "cam-1", _components(quality=0.1), frame_count=1, fps=5.0
        )

        assert payload is None

    @pytest.mark.asyncio
    async def test_suspected_spoof_reports_nothing(self, isolated_service):
        frame = np.zeros((64, 64, 3), dtype=np.uint8)

        payload = await process_ws_frame(
            frame, "cam-1", _components(is_live=False), frame_count=1, fps=5.0
        )

        assert payload is None


class TestWebSocketResilience:
    @pytest.mark.asyncio
    async def test_frame_failure_does_not_drop_the_connection(
        self, isolated_service, monkeypatch
    ):
        """The reported bug: a recognition-pipeline exception closed the
        WebSocket, and the kiosk rendered that as "Camera unavailable".

        The first frame raises; the second must still be processed and
        answered on the SAME connection.
        """
        calls = {"n": 0}

        async def flaky_pipeline(frame, camera_id, components, frame_count, fps):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ValueError("too many values to unpack (expected 2)")
            return {"type": "recognition", "member_name": "Juan Cardona"}

        monkeypatch.setattr(main, "process_ws_frame", flaky_pipeline)
        monkeypatch.setattr(main, "build_ws_pipeline_components", lambda: _components())
        # Frames arrive back-to-back in tests; advance the clock past the
        # 5fps throttle so the second frame isn't skipped as too-soon.
        clock = iter(range(1, 100))
        monkeypatch.setattr(main.time, "time", lambda: float(next(clock)))

        websocket = _FakeWebSocket([_jpeg_frame(), _jpeg_frame()])

        await websocket_camera_feed(websocket, "cam-1")

        assert calls["n"] == 2, "the second frame must still reach the pipeline"
        assert websocket.sent == [
            {"type": "recognition", "member_name": "Juan Cardona"}
        ]
        assert websocket.close_code is None, "a frame error must not close the socket"

    @pytest.mark.asyncio
    async def test_undecodable_frame_is_skipped_without_dropping_connection(
        self, isolated_service, monkeypatch
    ):
        monkeypatch.setattr(
            main,
            "process_ws_frame",
            AsyncMock(return_value={"type": "status", "faces": 0}),
        )
        monkeypatch.setattr(main, "build_ws_pipeline_components", lambda: _components())
        clock = iter(range(1, 100))
        monkeypatch.setattr(main.time, "time", lambda: float(next(clock)))

        websocket = _FakeWebSocket([b"not-a-jpeg", _jpeg_frame()])

        await websocket_camera_feed(websocket, "cam-1")

        assert websocket.sent == [{"type": "status", "faces": 0}]
        assert websocket.close_code is None
