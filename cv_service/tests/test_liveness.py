"""
Tests for liveness detector.

Fail-closed contract (WS-7a): every uncertain state — cascade missing,
fewer than two eyes, EAR computation failure, baseline collection — must
return NOT live, and a static (never-blinking) face must never become
live. Positive liveness requires a detected blink.
"""
import pytest
import numpy as np
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detection.liveness_detector import LivenessDetector


def _eye_roi():
    """A small non-empty ROI standing in for a detected eye."""
    return np.zeros((20, 20, 3), dtype=np.uint8)


class TestLivenessDetector:
    """Test anti-spoofing liveness detection."""

    def test_init(self):
        """Detector should initialize."""
        detector = LivenessDetector()
        assert detector.ear_threshold == 0.21
        assert detector.history_length == 30

    def test_missing_cascade_is_not_live(self):
        """Cascade-missing must FAIL CLOSED, never pass (WS-7a)."""
        detector = LivenessDetector()
        detector._eye_cascade = None
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        is_live, details = detector.check_liveness(frame, frame, (0, 0, 100, 100))
        assert is_live is False
        assert details["reason"] == "eye cascade not loaded"

    def test_single_eye_is_not_live(self):
        """One visible eye cannot prove a blink — deny (WS-7a)."""
        detector = LivenessDetector()
        detector._eye_cascade = object()
        detector._detect_eyes = lambda frame, bbox: [_eye_roi()]
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        is_live, details = detector.check_liveness(frame, frame, (0, 0, 100, 100))
        assert is_live is False
        assert details["reason"] == "insufficient_eyes"
        assert details["eyes_found"] == 1

    def test_no_eyes_is_not_live(self):
        """No eyes at all must be denied, not passed (WS-7a)."""
        detector = LivenessDetector()
        detector._eye_cascade = object()
        detector._detect_eyes = lambda frame, bbox: []
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        is_live, details = detector.check_liveness(frame, frame, (0, 0, 100, 100))
        assert is_live is False
        assert details["reason"] == "insufficient_eyes"
        assert details["eyes_found"] == 0

    def test_ear_computation_failure_is_not_live(self):
        """EAR failure must be denied, never passed (WS-7a)."""
        detector = LivenessDetector()
        detector._eye_cascade = object()
        detector._detect_eyes = lambda frame, bbox: [_eye_roi(), _eye_roi()]
        detector._compute_ear = lambda roi: None
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        is_live, details = detector.check_liveness(frame, frame, (0, 0, 100, 100))
        assert is_live is False
        assert details["reason"] == "ear_computation_failed"

    def test_baseline_frames_are_not_live(self):
        """Grace frames are ZERO: no recognition before positive evidence."""
        detector = LivenessDetector()
        detector._eye_cascade = object()
        detector._detect_eyes = lambda frame, bbox: [_eye_roi(), _eye_roi()]
        detector._compute_ear = lambda roi: 0.3
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        for _ in range(4):
            is_live, details = detector.check_liveness(frame, frame, (0, 0, 100, 100))
            assert is_live is False
            assert details["reason"] == "collecting_baseline"

    def test_static_never_blinking_face_never_live(self):
        """A photo has constant EAR — eyes continuously open must NOT pass.

        The 5th frame completes the baseline; without a blink the answer
        must stay False forever (regression guard for the removed
        ``avg_ear > threshold`` pass).
        """
        detector = LivenessDetector()
        detector._eye_cascade = object()
        detector._detect_eyes = lambda frame, bbox: [_eye_roi(), _eye_roi()]
        detector._compute_ear = lambda roi: 0.3  # wide-open, constant
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        for _ in range(12):
            is_live, details = detector.check_liveness(frame, frame, (0, 0, 100, 100))
            assert is_live is False, (
                f"static face became live at frame {details}"
            )

    def test_blink_sequence_becomes_live(self):
        """A real blink (EAR dip >= consecutive_frames) unlocks liveness."""
        detector = LivenessDetector()
        detector._eye_cascade = object()
        detector._detect_eyes = lambda frame, bbox: [_eye_roi(), _eye_roi()]
        detector._compute_ear = lambda roi: detector._current_ear
        detector._current_ear = 0.3
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        bbox = (0, 0, 100, 100)

        # Baseline (not live)
        for _ in range(5):
            is_live, _ = detector.check_liveness(frame, frame, bbox)
        assert is_live is False

        # Blink: EAR dips below threshold for consecutive_frames
        detector._current_ear = 0.1
        is_live, _ = detector.check_liveness(frame, frame, bbox)
        assert is_live is False
        detector._current_ear = 0.1
        is_live, _ = detector.check_liveness(frame, frame, bbox)
        assert is_live is False

        # Eyes reopen -> blink counted -> live
        detector._current_ear = 0.3
        is_live, details = detector.check_liveness(frame, frame, bbox)
        assert is_live is True
        assert details["blink_count"] == 1

    def test_reset(self):
        """Reset should clear all tracking."""
        detector = LivenessDetector()
        detector._ear_history['test'] = [0.3, 0.2, 0.3]
        detector._blink_counts['test'] = 1
        detector.reset()
        assert len(detector._ear_history) == 0
        assert len(detector._blink_counts) == 0

    def test_detectors_do_not_share_blink_state(self):
        """Two instances must never share EAR/blink state (cross-stream fix).

        A blink recorded on one detector must not unlock another.
        """
        a = LivenessDetector()
        b = LivenessDetector()
        a._ear_history["0_0"] = [0.3] * 5
        a._blink_counts["0_0"] = 3
        a._closed_frames["0_0"] = 0
        assert b._ear_history == {}
        assert b._blink_counts == {}
        assert b._closed_frames == {}

    def test_ear_computation_empty(self):
        """Empty ROI should return None EAR."""
        detector = LivenessDetector()
        result = detector._compute_ear(np.zeros((0, 0, 3), dtype=np.uint8))
        assert result is None
