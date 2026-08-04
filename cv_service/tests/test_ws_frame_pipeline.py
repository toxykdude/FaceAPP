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
from unittest.mock import AsyncMock, Mock

import cv2
import numpy as np
import pytest
from fastapi import WebSocketDisconnect
from pydantic import ValidationError

import main
from config import LivenessMode, Settings
from detection.liveness_detector import LivenessDetector
from main import (
    WS_NO_FACE_RESET_FRAMES,
    WsAttemptState,
    WsPipelineComponents,
    process_ws_frame,
    websocket_camera_feed,
)


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
    liveness_details=None,
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
            check_liveness=Mock(return_value=(is_live, liveness_details or {})),
            reset=Mock(),
        ),
        recognizer=SimpleNamespace(
            generate_embedding=Mock(return_value=np.zeros(512, dtype=np.float32)),
        ),
        matcher=SimpleNamespace(find_match=Mock(return_value=match)),
    )


def _attempt_state():
    return WsAttemptState(connection_id="connection-test", attempt_id="attempt-test")


def _messages(info, warning):
    return [call.args[0] for call in info.call_args_list + warning.call_args_list]


async def _process(
    frame,
    components,
    attempt_state=None,
    frame_count=1,
    fps=5.0,
    camera_id="cam-1",
):
    return await process_ws_frame(
        frame, camera_id, components, frame_count, fps,
        attempt_state or _attempt_state(),
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
    monkeypatch.setattr(main.settings, "WS_LIVENESS_MODE", LivenessMode.ENFORCE)
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

        payload = await _process(frame, _components())

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

        payload = await _process(frame, _components())

        assert payload["access_granted"] is False
        assert payload["denial_reason"] == "expired_membership"
        assert payload["days_remaining"] is None

    @pytest.mark.asyncio
    async def test_status_payload_when_no_face_present(self, isolated_service):
        frame = np.zeros((64, 64, 3), dtype=np.uint8)

        payload = await _process(frame, _components(faces=None), frame_count=7)

        assert payload == {
            "type": "status",
            "fps": 5.0,
            "frames_processed": 7,
            "faces": 0,
        }

    @pytest.mark.asyncio
    async def test_low_quality_frame_reports_nothing(self, isolated_service):
        frame = np.zeros((64, 64, 3), dtype=np.uint8)

        payload = await _process(frame, _components(quality=0.1))

        assert payload is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "liveness_details", [{}, {"reason": "insufficient_evidence"}]
    )
    async def test_enforce_blocks_failed_or_indeterminate_liveness(
        self, isolated_service, liveness_details
    ):
        frame = np.zeros((64, 64, 3), dtype=np.uint8)

        components = _components(is_live=False, liveness_details=liveness_details)
        payload = await _process(frame, components)

        assert payload is None
        components.recognizer.generate_embedding.assert_not_called()
        components.matcher.find_match.assert_not_called()
        isolated_service.validator.validate_access.assert_not_awaited()
        components.liveness_detector.reset.assert_not_called()

    @pytest.mark.parametrize(
        ("mode", "expected_evaluator_calls"),
        [(LivenessMode.OBSERVE, 5), (LivenessMode.DISABLED, 0)],
    )
    @pytest.mark.asyncio
    async def test_repeated_non_enforcing_frames_bound_telemetry(
        self, isolated_service, monkeypatch, mode, expected_evaluator_calls
    ):
        monkeypatch.setattr(main.settings, "WS_LIVENESS_MODE", mode)
        info = Mock()
        warning = Mock()
        monkeypatch.setattr(main.logger, "info", info)
        monkeypatch.setattr(main.logger, "warning", warning)
        components = _components(
            is_live=False,
            liveness_details={
                "reason": "insufficient_evidence",
                "private_detector_detail": "not-for-telemetry",
            },
            match=(
                "member-sensitive-value",
                0.93,
                {"name": "member-sensitive-value"},
            ),
        )
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        attempt_state = _attempt_state()

        for _ in range(5):
            payload = await _process(frame, components, attempt_state)
            assert payload["type"] == "recognition"

        telemetry = " ".join(_messages(info, warning))
        assert telemetry.count("stage=evaluation") == 1
        assert telemetry.count("stage=terminal_response") == 1
        assert "stage=reset" not in telemetry
        assert "member-sensitive-value" not in telemetry
        assert "not-for-telemetry" not in telemetry
        assert (
            components.liveness_detector.check_liveness.call_count
            == expected_evaluator_calls
        )
        assert components.recognizer.generate_embedding.call_count == 5

    @pytest.mark.asyncio
    async def test_enforce_terminal_result_resets_liveness_state(self, isolated_service):
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        components = _components()
        attempt_state = _attempt_state()

        payload = await _process(frame, components, attempt_state)

        assert payload["type"] == "recognition"
        components.liveness_detector.reset.assert_called_once()
        assert attempt_state.attempt_id != "attempt-test"

    @pytest.mark.asyncio
    async def test_observe_accumulates_and_completes_stateful_blink(
        self, isolated_service, monkeypatch
    ):
        monkeypatch.setattr(main.settings, "WS_LIVENESS_MODE", LivenessMode.OBSERVE)
        info = Mock()
        warning = Mock()
        monkeypatch.setattr(main.logger, "info", info)
        monkeypatch.setattr(main.logger, "warning", warning)
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        detector = LivenessDetector()
        detector._eye_rois_from_landmarks = Mock(return_value=[frame[:8, :8]] * 2)
        detector._compute_ear = Mock(
            side_effect=[0.4, 0.4] * 5 + [0.1, 0.1] + [0.4, 0.4]
        )
        detector.reset = Mock(wraps=detector.reset)
        components = _components()._replace(liveness_detector=detector)
        attempt_state = _attempt_state()

        for frame_count in range(1, 8):
            payload = await _process(frame, components, attempt_state, frame_count)
            assert payload["type"] == "recognition"

        telemetry = _messages(info, warning)
        assert sum("outcome=pass" in message for message in telemetry) == 1
        assert components.recognizer.generate_embedding.call_count == 7
        assert isolated_service.validator.validate_access.await_count == 7
        assert detector._compute_ear.call_count == 14

        stage_count = sum("stage=" in message for message in telemetry)
        for frame_count in range(8, 11):
            await _process(frame, components, attempt_state, frame_count)
        later_telemetry = _messages(info, warning)
        assert sum("stage=" in message for message in later_telemetry) == stage_count
        assert detector._compute_ear.call_count == 14

        completed_attempt_id = attempt_state.attempt_id
        components.detector.detect_faces_with_landmarks = Mock(return_value=[])
        for frame_count in range(11, 11 + WS_NO_FACE_RESET_FRAMES):
            await _process(frame, components, attempt_state, frame_count)

        assert attempt_state.attempt_id != completed_attempt_id
        assert (detector.reset.call_count, attempt_state.observation_complete) == (2, False)


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

        async def flaky_pipeline(
            frame, camera_id, components, frame_count, fps, attempt_state
        ):
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
    async def test_disconnect_cleanup_resets_liveness_state(
        self, isolated_service, monkeypatch
    ):
        components = _components()
        monkeypatch.setattr(main, "build_ws_pipeline_components", lambda: components)
        websocket = _FakeWebSocket([])

        await websocket_camera_feed(websocket, "cam-1")

        components.liveness_detector.reset.assert_called_once()

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


class TestWsLivenessConfiguration:
    def test_default_mode_is_enforce(self):
        configured = Settings(_env_file=None)

        assert configured.WS_LIVENESS_MODE is LivenessMode.ENFORCE

    def test_invalid_mode_is_rejected(self):
        with pytest.raises(ValidationError):
            Settings(WS_LIVENESS_MODE="challenge", _env_file=None)
