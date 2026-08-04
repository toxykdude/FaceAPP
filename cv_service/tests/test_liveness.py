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
        assert detector.close_ratio == 0.6
        assert detector.reopen_ratio == 0.8
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
        """A relative close-open cycle unlocks liveness."""
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

        # Blink: EAR drops relative to each eye's baseline.
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

    def test_asymmetric_live_ear_sequence_detects_blink(self):
        """A live one-eye dip must not be hidden by averaging both eyes."""
        detector = LivenessDetector()
        detector._eye_cascade = object()
        detector._detect_eyes = lambda frame, bbox: [_eye_roi(), _eye_roi()]
        detector._current_ears = [0.584, 0.52]
        detector._compute_ear = lambda roi: detector._current_ears.pop(0)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        bbox = (0, 0, 100, 100)

        for _ in range(5):
            detector._current_ears = [0.584, 0.52]
            is_live, _ = detector.check_liveness(frame, frame, bbox)
        assert is_live is False

        # Live DEV evidence: averaging these values yields 0.330, above the
        # old absolute threshold, while the right eye is clearly closed.
        detector._current_ears = [0.584, 0.077]
        is_live, _ = detector.check_liveness(frame, frame, bbox)
        assert is_live is False

        detector._current_ears = [0.58, 0.51]
        is_live, details = detector.check_liveness(frame, frame, bbox)
        assert is_live is True
        assert details["blink_count"] == 1
        assert details["eye_baselines"] == [0.584, 0.52]

    def test_closed_baseline_outlier_does_not_pollute_median(self):
        """One closed sample during calibration must not lower the open baseline."""
        detector = LivenessDetector()
        detector._eye_cascade = object()
        detector._detect_eyes = lambda frame, bbox: [_eye_roi(), _eye_roi()]
        detector._compute_ear = lambda roi: detector._current_ears.pop(0)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        bbox = (0, 0, 100, 100)

        for right_ear in [0.52, 0.52, 0.077, 0.52, 0.52]:
            detector._current_ears = [0.584, right_ear]
            is_live, _ = detector.check_liveness(frame, frame, bbox)
            assert is_live is False

        detector._current_ears = [0.584, 0.077]
        is_live, _ = detector.check_liveness(frame, frame, bbox)
        assert is_live is False
        detector._current_ears = [0.584, 0.52]
        is_live, details = detector.check_liveness(frame, frame, bbox)
        assert is_live is True
        assert details["eye_baselines"] == [0.584, 0.52]

    def test_invalid_frame_breaks_close_to_open_transition(self):
        """Garbage between closure and reopening cannot be stitched into a blink."""
        detector = LivenessDetector()
        detector._eye_cascade = object()
        detector._detect_eyes = lambda frame, bbox: [_eye_roi(), _eye_roi()]
        detector._compute_ear = lambda roi: detector._current_ears.pop(0)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        bbox = (0, 0, 100, 100)

        for _ in range(5):
            detector._current_ears = [0.584, 0.52]
            detector.check_liveness(frame, frame, bbox)

        detector._current_ears = [0.584, 0.077]
        is_live, _ = detector.check_liveness(frame, frame, bbox)
        assert is_live is False
        detector._current_ears = [0.584, None]
        is_live, details = detector.check_liveness(frame, frame, bbox)
        assert is_live is False
        assert details["reason"] == "ear_computation_failed"
        detector._current_ears = [0.584, 0.52]
        is_live, details = detector.check_liveness(frame, frame, bbox)
        assert is_live is False
        assert details["blink_count"] == 0

    def test_missing_eye_breaks_close_to_open_transition(self):
        """A partial detection cannot bridge closure and reopening."""
        detector = LivenessDetector()
        detector._eye_cascade = object()
        detector._eye_count = 2
        detector._detect_eyes = lambda frame, bbox: [
            _eye_roi() for _ in range(detector._eye_count)
        ]
        detector._compute_ear = lambda roi: detector._current_ear
        detector._current_ear = 0.3
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        bbox = (0, 0, 100, 100)

        for _ in range(5):
            detector.check_liveness(frame, frame, bbox)
        detector._current_ear = 0.1
        is_live, _ = detector.check_liveness(frame, frame, bbox)
        assert is_live is False

        detector._eye_count = 1
        is_live, details = detector.check_liveness(frame, frame, bbox)
        assert is_live is False
        assert details["reason"] == "insufficient_eyes"

        detector._eye_count = 2
        detector._current_ear = 0.3
        is_live, details = detector.check_liveness(frame, frame, bbox)
        assert is_live is False
        assert details["blink_count"] == 0

    def test_one_valid_ear_is_insufficient_evidence(self):
        """A failed eye measurement must remain denied and not calibrate state."""
        detector = LivenessDetector()
        detector._eye_cascade = object()
        detector._detect_eyes = lambda frame, bbox: [_eye_roi(), _eye_roi()]
        values = iter([0.58, None])
        detector._compute_ear = lambda roi: next(values)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)

        is_live, details = detector.check_liveness(frame, frame, (0, 0, 100, 100))

        assert is_live is False
        assert details["reason"] == "ear_computation_failed"
        assert details["ears_computed"] == 1
        assert detector._ear_history == {}

    def test_reset(self):
        """Reset should clear all tracking."""
        detector = LivenessDetector()
        detector._ear_history["test"] = [0.3, 0.2, 0.3]
        detector._eye_baselines["test"] = [[0.3], [0.3]]
        detector._blink_counts["test"] = 1
        detector._closed_frames["test"] = [1, 0]
        detector._face_boxes["test"] = (0, 0, 100, 100)
        detector._next_face_key = 4
        detector.reset()
        assert detector._ear_history == {}
        assert detector._eye_baselines == {}
        assert detector._blink_counts == {}
        assert detector._closed_frames == {}
        assert detector._face_boxes == {}
        assert detector._next_face_key == 0

    def test_detectors_do_not_share_blink_state(self):
        """Two instances must never share EAR/blink state (cross-stream fix).

        A blink recorded on one detector must not unlock another.
        """
        a = LivenessDetector()
        b = LivenessDetector()
        a._ear_history["0_0"] = [0.3] * 5
        a._eye_baselines["0_0"] = [[0.3] * 5, [0.3] * 5]
        a._blink_counts["0_0"] = 3
        a._closed_frames["0_0"] = [0, 0]
        assert b._ear_history == {}
        assert b._eye_baselines == {}
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

    def test_cascade_eye_order_is_stable_left_to_right(self):
        """Cascade detection order must not swap independent eye baselines."""
        detector = LivenessDetector()

        class ReversedCascade:
            def detectMultiScale(self, *args, **kwargs):
                return np.array([[60, 5, 20, 20], [10, 5, 20, 20]])

        detector._eye_cascade = ReversedCascade()
        face = np.zeros((60, 100, 3), dtype=np.uint8)
        face[5:25, 10:30] = 10
        face[5:25, 60:80] = 20

        rois = detector._detect_eyes(face, (0, 0, 100, 60))

        assert [int(roi[0, 0, 0]) for roi in rois] == [10, 20]

    def test_landmark_eye_order_preserves_mtcnn_contract(self):
        """Landmark ROIs must preserve MTCNN's left-eye, right-eye ordering."""
        detector = LivenessDetector()
        frame = np.zeros((100, 140, 3), dtype=np.uint8)
        frame[30, 30] = 10
        frame[30, 110] = 20
        landmarks = np.array(
            [[30, 30], [110, 30], [70, 50], [50, 75], [90, 75]], dtype=float
        )

        rois = detector._eye_rois_from_landmarks(
            frame, (10, 10, 120, 80), landmarks
        )

        assert int(rois[0].max()) == 10
        assert int(rois[1].max()) == 20

    def test_face_key_stable_under_bbox_jitter(self):
        """BBox jitter must not reset tracking history (regression).

        The old top-left quantization (x//50, y//50) made every jittering
        frame open a new face key, so "collecting_baseline" never finished.
        """
        detector = LivenessDetector()
        detector._eye_cascade = object()
        detector._detect_eyes = lambda frame, bbox: [_eye_roi(), _eye_roi()]
        detector._compute_ear = lambda roi: detector._current_ear
        detector._current_ear = 0.3
        frame = np.zeros((200, 200, 3), dtype=np.uint8)
        bboxes = [(100, 100, 100, 100), (102, 98, 100, 100), (99, 101, 100, 100)]

        for i in range(5):
            bbox = bboxes[i % 3]
            is_live, _ = detector.check_liveness(frame, frame, bbox)
            assert is_live is False

        detector._current_ear = 0.1
        is_live, _ = detector.check_liveness(frame, frame, bboxes[2])
        assert is_live is False
        detector._current_ear = 0.3
        is_live, details = detector.check_liveness(frame, frame, bboxes[0])
        assert is_live is True
        assert details["blink_count"] == 1
        assert len(detector._ear_history) == 1
        assert len(next(iter(detector._ear_history.values()))) == 7

    def test_realistic_center_and_scale_jitter_completes_blink(self):
        """Largest-face motion and scale jitter must retain one baseline."""
        detector = LivenessDetector()
        detector._eye_cascade = object()
        detector._detect_eyes = lambda frame, bbox: [_eye_roi(), _eye_roi()]
        detector._compute_ear = lambda roi: detector._current_ear
        detector._current_ear = 0.3
        frame = np.zeros((300, 300, 3), dtype=np.uint8)
        bboxes = [
            (80, 70, 120, 140),
            (94, 79, 110, 130),
            (72, 62, 132, 152),
            (88, 72, 116, 136),
            (76, 66, 126, 146),
        ]

        for bbox in bboxes:
            is_live, _ = detector.check_liveness(frame, frame, bbox)
            assert is_live is False

        detector._current_ear = 0.1
        is_live, _ = detector.check_liveness(frame, frame, (96, 80, 108, 128))
        assert is_live is False
        detector._current_ear = 0.3
        is_live, details = detector.check_liveness(
            frame, frame, (70, 60, 134, 154)
        )

        assert is_live is True
        assert details["blink_count"] == 1
        assert len(detector._face_boxes) == 1

    def test_distant_face_cannot_inherit_liveness_state(self):
        """An implausible jump must start isolated baseline and blink state."""
        detector = LivenessDetector()
        first_key = detector._get_face_key((10, 10, 100, 100))
        detector._eye_baselines[first_key] = [[0.3] * 5, [0.3] * 5]
        detector._blink_counts[first_key] = 1

        second_key = detector._get_face_key((500, 400, 100, 100))

        assert second_key != first_key
        assert second_key not in detector._eye_baselines
        assert second_key not in detector._blink_counts

    def test_nearest_compatible_track_wins(self):
        """Association must choose geometry, not dict insertion order."""
        detector = LivenessDetector()
        first_key = "first"
        second_key = "second"
        detector._face_boxes[first_key] = (0, 0, 100, 100)
        detector._face_boxes[second_key] = (60, 0, 100, 100)

        matched_key = detector._get_face_key((40, 0, 100, 100))

        assert matched_key == second_key
        assert matched_key != first_key

    def test_face_tracking_state_is_bounded_with_bbox_cache(self):
        """Evicting a face bbox must evict every associated state map."""
        detector = LivenessDetector()
        for index in range(17):
            key = detector._get_face_key((index * 100, 0, 40, 40))
            detector._ear_history[key] = [0.3]
            detector._eye_baselines[key] = [[0.3], [0.3]]
            detector._blink_counts[key] = 0
            detector._closed_frames[key] = [0, 0]

        assert len(detector._face_boxes) == 16
        assert len(detector._ear_history) == 16
        assert len(detector._eye_baselines) == 16
        assert len(detector._blink_counts) == 16
        assert len(detector._closed_frames) == 16

    def test_unmatched_centers_in_same_cell_do_not_reuse_state(self):
        """A quantization collision must not inherit another face's liveness."""
        detector = LivenessDetector()
        first_key = detector._get_face_key((0, 0, 2, 2))
        detector._blink_counts[first_key] = 1

        second_key = detector._get_face_key((38, 38, 2, 2))

        assert second_key != first_key
        assert second_key not in detector._blink_counts

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
