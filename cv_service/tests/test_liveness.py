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
        assert detector.consecutive_frames == 1
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
            assert is_live is False, f"static face became live at frame {details}"

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
        detector._ear_history["test"] = [0.3, 0.2, 0.3]
        detector._blink_counts["test"] = 1
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

    def test_ear_normalized_and_plausibility_gated(self):
        """EAR must be axis-normalized (<= 1.0) and implausible shapes rejected.

        Regression: fitEllipse may report a tall blob with major < minor,
        producing EAR values > 1 (observed 1.5-10.3 on a real face), which
        made blinks unobservable. Needle-like and near-circular contours are
        not eyes: they must yield None so the caller fails closed.
        """
        detector = LivenessDetector()
        import cv2

        # Vertical ellipse (w=6, h=12): whichever axis order fitEllipse
        # reports, normalized EAR must be ~0.5 and never exceed 1.0.
        img = np.full((60, 60), 255, dtype=np.uint8)
        cv2.ellipse(img, (30, 30), (6, 12), 0, 0, 360, 0, -1)
        ear = detector._compute_ear(img)
        assert ear is not None
        assert 0.0 < ear <= 1.0
        assert abs(ear - 0.5) < 0.15

        # Needle-like contour (1x44) -> implausible -> None
        img2 = np.full((60, 60), 255, dtype=np.uint8)
        cv2.ellipse(img2, (30, 30), (1, 44), 0, 0, 360, 0, -1)
        assert detector._compute_ear(img2) is None

        # Near-circular blob -> implausible -> None
        img3 = np.full((60, 60), 255, dtype=np.uint8)
        cv2.circle(img3, (30, 30), 12, 0, -1)
        assert detector._compute_ear(img3) is None

    def test_eye_rois_from_landmarks_anchor_on_centers(self):
        """Landmark-anchored ROIs crop around the MTCNN eye centers."""
        detector = LivenessDetector()
        frame = np.zeros((200, 240, 3), dtype=np.uint8)
        frame[80, 70] = 255  # left eye center
        frame[80, 170] = 255  # right eye center
        landmarks = np.array(
            [[70, 80], [170, 80], [120, 110], [95, 140], [145, 140]], dtype=float
        )
        bbox = (40, 60, 160, 120)

        rois = detector._eye_rois_from_landmarks(frame, bbox, landmarks)
        assert len(rois) == 2
        # eye_w = 48, eye_h = 21 for this face
        for roi in rois:
            assert roi.shape == (21, 48, 3)
            assert roi.max() == 255  # the bright eye pixel falls inside

        # Clamped at frame borders
        border_landmarks = np.array(
            [[2, 2], [230, 180], [120, 110], [95, 140], [145, 140]], dtype=float
        )
        rois = detector._eye_rois_from_landmarks(frame, bbox, border_landmarks)
        assert rois[0].shape == (21, 48, 3)  # left: clamped to (0, 0)
        assert rois[1].shape == (21, 34, 3)  # right: clamped to frame width

        # No landmarks -> no ROIs
        assert detector._eye_rois_from_landmarks(frame, bbox, None) == []

    def test_face_key_stable_under_bbox_jitter(self):
        """BBox jitter must not reset tracking history (regression).

        The old top-left quantization (x//50, y//50) made every jittering
        frame open a new face key, so "collecting_baseline" never finished.
        """
        detector = LivenessDetector()
        detector._eye_cascade = object()
        detector._detect_eyes = lambda frame, bbox: [_eye_roi(), _eye_roi()]
        detector._compute_ear = lambda roi: 0.3
        frame = np.zeros((200, 200, 3), dtype=np.uint8)
        bboxes = [(100, 100, 100, 100), (102, 98, 100, 100), (99, 101, 100, 100)]

        for i in range(10):
            bbox = bboxes[i % 3]
            is_live, _ = detector.check_liveness(frame, frame, bbox)
            assert is_live is False

        assert len(detector._ear_history) == 1
        assert len(next(iter(detector._ear_history.values()))) == 10

    def test_landmark_path_works_without_cascade(self):
        """Landmark-anchored eye ROIs work even if the cascade is missing."""
        detector = LivenessDetector()
        detector._eye_cascade = None
        detector._compute_ear = lambda roi: detector._current_ear
        detector._current_ear = 0.3
        frame = np.zeros((200, 240, 3), dtype=np.uint8)
        bbox = (40, 60, 160, 120)
        landmarks = np.array(
            [[70, 80], [170, 80], [120, 110], [95, 140], [145, 140]], dtype=float
        )

        for _ in range(5):
            is_live, _ = detector.check_liveness(frame, frame, bbox, landmarks)
        assert is_live is False

        detector._current_ear = 0.1  # blink
        is_live, _ = detector.check_liveness(frame, frame, bbox, landmarks)
        assert is_live is False

        detector._current_ear = 0.3  # reopen -> blink counted
        is_live, details = detector.check_liveness(frame, frame, bbox, landmarks)
        assert is_live is True
        assert details["blink_count"] == 1

    def test_blink_single_low_frame_registers(self):
        """A single closed frame counts as a blink at 5fps.

        Natural blinks (100-400ms) span 1-2 frames at the pipeline frame
        rate; requiring 2 consecutive closed frames lost most real blinks.
        """
        detector = LivenessDetector()
        detector._eye_cascade = object()
        detector._detect_eyes = lambda frame, bbox: [_eye_roi(), _eye_roi()]
        detector._compute_ear = lambda roi: detector._current_ear
        detector._current_ear = 0.3
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        bbox = (0, 0, 100, 100)

        for _ in range(5):
            is_live, _ = detector.check_liveness(frame, frame, bbox)
        assert is_live is False

        detector._current_ear = 0.1
        is_live, _ = detector.check_liveness(frame, frame, bbox)
        assert is_live is False

        detector._current_ear = 0.3
        is_live, details = detector.check_liveness(frame, frame, bbox)
        assert is_live is True
        assert details["blink_count"] == 1
