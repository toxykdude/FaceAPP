"""
Liveness detection module using Eye Aspect Ratio (EAR) for anti-spoofing.

Detects natural eye blinks to distinguish live faces from photos/videos.
Eye ROIs are anchored on the MTCNN 5-point landmarks (eye centers) when the
pipeline provides them, falling back to the Haar eye cascade. A blink
(EAR dip below threshold, then recovery) unlocks liveness.

Fail-closed contract: every uncertain state — no eye evidence, EAR
computation failure, implausible EAR, baseline collection — denies
liveness. Only a detected blink passes.
"""

import cv2
import numpy as np
from typing import Optional, Tuple, List
from loguru import logger


class LivenessDetector:
    """
    Anti-spoofing via blink detection using Eye Aspect Ratio.

    A real person blinks naturally (EAR drops below threshold then rises).
    A photo or screen has constant EAR (no blink).
    """

    def __init__(
        self,
        close_ratio: float = 0.6,
        reopen_ratio: float = 0.8,
        consecutive_frames: int = 1,
        history_length: int = 30,
    ):
        """
        Args:
            close_ratio: Eye is closed below this fraction of its open baseline.
            reopen_ratio: Eye has reopened above this fraction of its baseline.
            consecutive_frames: How many consecutive low-EAR frames count as a
                blink.
                Defaults to 1: at the pipeline's 5fps budget a natural blink
                (100-400ms) spans 1-2 frames, so requiring 2 lost most real
                blinks and the kiosk never unlocked. A photo's EAR is constant,
                so a single dip still never passes a static face.
            history_length: How many EAR values to track
        """
        self.close_ratio = close_ratio
        self.reopen_ratio = reopen_ratio
        self.consecutive_frames = consecutive_frames
        self.history_length = history_length

        # EAR history per tracked face (keyed by face position hash)
        self._ear_history: dict = {}
        self._eye_baselines: dict = {}
        self._blink_counts: dict = {}
        self._closed_frames: dict = {}
        # Last-seen center per face key, for stable tracking
        self._face_centers: dict = {}

        # Load face landmark detector
        self._landmark_detector = None
        self._init_landmark_detector()

    def _init_landmark_detector(self):
        """Initialize facial landmark detector."""
        try:
            # Use OpenCV's FaceDetectorYN with landmarks if available
            # Fallback: use simple contour-based eye detection
            cascade_path = cv2.data.haarcascades + "haarcascade_eye.xml"
            self._eye_cascade = cv2.CascadeClassifier(cascade_path)
            if self._eye_cascade.empty():
                logger.warning("Could not load eye cascade — liveness disabled")
                self._eye_cascade = None
            else:
                logger.info("Liveness detector initialized (eye cascade)")
        except Exception as e:
            logger.warning(f"Liveness detector init failed: {e}")
            self._eye_cascade = None

    def _compute_ear(self, eye_roi: np.ndarray) -> Optional[float]:
        """
        Compute Eye Aspect Ratio for a single eye ROI.

        Uses contour-based approach:
        1. Threshold and find contours
        2. Fit ellipse to largest contour
        3. EAR = minor_axis / major_axis (axes normalized: minor <= major)

        Returns:
            EAR value (0.0-1.0) or None if can't compute / implausible shape
        """
        if eye_roi.size == 0:
            return None

        try:
            gray = (
                cv2.cvtColor(eye_roi, cv2.COLOR_BGR2GRAY)
                if len(eye_roi.shape) == 3
                else eye_roi
            )
            gray = cv2.GaussianBlur(gray, (7, 7), 0)
            _, thresh = cv2.threshold(
                gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
            )

            contours, _ = cv2.findContours(
                thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            if not contours:
                return None

            # Get largest contour (the eye)
            largest = max(contours, key=cv2.contourArea)

            if len(largest) < 5:
                return None

            # Fit ellipse
            ellipse = cv2.fitEllipse(largest)
            _, (axis_a, axis_b), _ = ellipse

            # fitEllipse does NOT guarantee (width, height) ordering: for a
            # tall blob it reports minor > major, producing EAR values > 1
            # (observed 1.5-10.3 on a real face), which made blinks
            # unobservable. Normalize so EAR is always minor / major in (0, 1].
            major, minor = sorted((axis_a, axis_b), reverse=True)
            if major <= 0:
                return None

            ear = minor / major

            # Plausibility gate: a real open/closed eye sits roughly in
            # (0.05, 0.6). Near-circular or needle-like contours are NOT
            # eyes — return None so the caller FAILS CLOSED instead of
            # trusting a garbage ratio.
            if ear < 0.03 or ear > 0.92:
                return None

            return float(ear)
        except Exception:
            return None

    def _detect_eyes(self, face_roi: np.ndarray, face_bbox: tuple) -> List[np.ndarray]:
        """
        Detect eye ROIs from face region.

        Args:
            face_roi: Face region of interest
            face_bbox: Face bounding box (x, y, w, h)

        Returns:
            List of eye ROI images
        """
        if self._eye_cascade is None:
            return []

        try:
            gray = (
                cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
                if len(face_roi.shape) == 3
                else face_roi
            )
            h, w = gray.shape[:2]

            # Only search upper half of face for eyes
            upper_half = gray[: h // 2, :]

            eyes = self._eye_cascade.detectMultiScale(
                upper_half, scaleFactor=1.1, minNeighbors=5, minSize=(20, 20)
            )

            # Cascade result order is not stable. Keep a left-to-right contract
            # so each EAR is compared with the same eye's baseline every frame.
            eye_rois = []
            for ex, ey, ew, eh in sorted(eyes, key=lambda eye: eye[0])[:2]:
                eye_roi = face_roi[ey : ey + eh, ex : ex + ew]
                if eye_roi.size > 0:
                    eye_rois.append(eye_roi)

            return eye_rois
        except Exception:
            return []

    def _eye_rois_from_landmarks(
        self, frame: np.ndarray, face_bbox: tuple, landmarks
    ) -> List[np.ndarray]:
        """
        Crop eye ROIs anchored on the MTCNN 5-point landmarks.

        ``landmarks`` are full-frame (x, y) coordinates in MTCNN order:
        [left_eye, right_eye, nose, left_mouth, right_mouth]. Anchoring on
        the eye centers gives guaranteed on-eye crops that do not depend on
        the Haar cascade (which can latch onto eyebrows or fail on small
        face ROIs).

        Args:
            frame: Full camera frame
            face_bbox: Face bounding box (x, y, w, h)
            landmarks: 5-point MTCNN landmarks (full-frame coords) or None

        Returns:
            List of eye ROI images (left, right)
        """
        if landmarks is None or len(landmarks) < 2:
            return []

        _, _, w, h = face_bbox
        eye_w = max(24, int(w * 0.30))
        eye_h = max(16, int(h * 0.18))
        frame_h, frame_w = frame.shape[:2]

        rois = []
        for ex, ey in (landmarks[0], landmarks[1]):
            ex = int(round(float(ex)))
            ey = int(round(float(ey)))
            x1 = max(0, ex - eye_w // 2)
            y1 = max(0, ey - eye_h // 2)
            x2 = min(frame_w, x1 + eye_w)
            y2 = min(frame_h, y1 + eye_h)
            roi = frame[y1:y2, x1:x2]
            if roi.size > 0:
                rois.append(roi)
        return rois

    def _get_face_key(self, face_bbox: tuple) -> str:
        """
        Stable per-face tracking key.

        The top-left bbox corner jitters twice as much as the center and
        crosses quantization cells frame to frame, which reset the
        baseline/blink history forever (kiosk stuck on "collecting_baseline").
        Track by quantized CENTER, and reassign to a previously tracked face
        when its center moved by less than ~20% of the face width.
        """
        x, y, w, h = face_bbox
        cx, cy = x + w // 2, y + h // 2
        reassign_threshold = max(30.0, 0.2 * w)

        for key, (pcx, pcy) in self._face_centers.items():
            if (pcx - cx) ** 2 + (pcy - cy) ** 2 <= reassign_threshold**2:
                self._face_centers[key] = (cx, cy)
                return key

        base_key = f"{cx // 40}_{cy // 40}"
        key = base_key
        suffix = 1
        while key in self._face_centers:
            key = f"{base_key}_{suffix}"
            suffix += 1
        self._face_centers[key] = (cx, cy)
        if len(self._face_centers) > 16:
            # Bound memory on long-running kiosks.
            stale_key = next(iter(self._face_centers))
            self._face_centers.pop(stale_key)
            self._ear_history.pop(stale_key, None)
            self._eye_baselines.pop(stale_key, None)
            self._blink_counts.pop(stale_key, None)
            self._closed_frames.pop(stale_key, None)
        return key

    def check_liveness(
        self,
        frame: np.ndarray,
        face_roi: np.ndarray,
        face_bbox: tuple,
        landmarks: Optional[np.ndarray] = None,
    ) -> Tuple[bool, dict]:
        """
        Check if a face is live (real person) or spoof (photo/video).

        Args:
            frame: Full camera frame
            face_roi: Face region of interest
            face_bbox: Face bounding box (x, y, w, h)
            landmarks: Optional 5-point MTCNN landmarks (full-frame coords);
                when present, eye ROIs are anchored on the eye centers.

        Returns:
            Tuple of (is_live, details_dict)
        """
        details = {
            "ear_values": [],
            "blink_count": 0,
            "avg_ear": 0.0,
            "method": "blink_detection",
        }
        face_key = self._get_face_key(face_bbox)

        # Prefer landmark-anchored eye ROIs (does not need the cascade).
        eye_rois = self._eye_rois_from_landmarks(frame, face_bbox, landmarks)
        if not eye_rois:
            if self._eye_cascade is None:
                # No eye evidence source at all — FAIL CLOSED. A photo or a
                # broken detector must never unlock the door.
                if face_key in self._closed_frames:
                    self._closed_frames[face_key] = [0, 0]
                return False, {"method": "disabled", "reason": "eye cascade not loaded"}
            # Detect eyes
            eye_rois = self._detect_eyes(face_roi, face_bbox)

        if len(eye_rois) < 2:
            # Both eyes are required to compute a blink. A face with a
            # single visible eye (or none) cannot be proven live — deny.
            if face_key in self._closed_frames:
                self._closed_frames[face_key] = [0, 0]
            return False, {
                "method": "blink_detection",
                "reason": "insufficient_eyes",
                "eyes_found": len(eye_rois),
            }

        # Compute EAR for both eyes
        ears = []
        for eye_roi in eye_rois:
            ear = self._compute_ear(eye_roi)
            if ear is not None:
                ears.append(ear)

        if len(ears) != 2:
            # Both eyes need valid measurements. Partial or garbage evidence
            # cannot calibrate a trustworthy per-eye baseline or bridge a
            # close-to-open transition across an uncertain frame.
            if face_key in self._closed_frames:
                self._closed_frames[face_key] = [0, 0]
            return False, {
                "method": "blink_detection",
                "reason": "ear_computation_failed",
                "ears_computed": len(ears),
            }

        avg_ear = sum(ears) / len(ears)

        # Initialize tracking for new face
        if face_key not in self._ear_history:
            self._ear_history[face_key] = []
            self._eye_baselines[face_key] = [[], []]
            self._blink_counts[face_key] = 0
            self._closed_frames[face_key] = [0, 0]

        # Add EAR to history
        history = self._ear_history[face_key]
        history.append(avg_ear)
        if len(history) > self.history_length:
            history.pop(0)

        baselines = self._eye_baselines[face_key]
        if len(history) <= 5:
            for index, ear in enumerate(ears):
                baselines[index].append(ear)
        else:
            blink_detected = False
            for index, ear in enumerate(ears):
                baseline = float(np.median(baselines[index]))
                if ear < baseline * self.close_ratio:
                    self._closed_frames[face_key][index] += 1
                elif ear >= baseline * self.reopen_ratio:
                    if (
                        self._closed_frames[face_key][index]
                        >= self.consecutive_frames
                    ):
                        blink_detected = True
                    self._closed_frames[face_key][index] = 0
            if blink_detected:
                self._blink_counts[face_key] += 1

        # Need at least 5 frames of history to make a determination.
        # Grace frames are ZERO: until positive liveness evidence exists,
        # no recognition is allowed.
        if len(history) < 5:
            return False, {
                "method": "blink_detection",
                "reason": "collecting_baseline",
                "frames_collected": len(history),
                "blink_count": self._blink_counts[face_key],
                "avg_ear": round(avg_ear, 3),
            }

        blink_count = self._blink_counts[face_key]
        # Positive liveness requires a detected blink. A photo never blinks
        # (its EAR is constant), so "eyes continuously open" is NOT a pass.
        is_live = blink_count >= 1

        details = {
            "method": "blink_detection",
            "is_live": is_live,
            "blink_count": blink_count,
            "avg_ear": round(avg_ear, 3),
            "ear_values": [round(e, 3) for e in ears],
            "eye_baselines": [
                round(float(np.median(values)), 3) for values in baselines
            ],
            "frames_tracked": len(history),
        }

        return is_live, details

    def reset(self):
        """Reset all tracking state."""
        self._ear_history.clear()
        self._eye_baselines.clear()
        self._blink_counts.clear()
        self._closed_frames.clear()
        self._face_centers.clear()


# Global instance
liveness_detector = LivenessDetector()
