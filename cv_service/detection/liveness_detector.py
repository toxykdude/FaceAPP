"""
Liveness detection module using Eye Aspect Ratio (EAR) for anti-spoofing.

Detects natural eye blinks to distinguish live faces from photos/videos.
Uses facial landmarks (dlib or OpenCV) to compute EAR over consecutive frames.
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
    
    def __init__(self, 
                 ear_threshold: float = 0.21,
                 consecutive_frames: int = 2,
                 history_length: int = 30):
        """
        Args:
            ear_threshold: EAR below this = eye is closed
            consecutive_frames: How many consecutive low-EAR frames count as a blink
            history_length: How many EAR values to track
        """
        self.ear_threshold = ear_threshold
        self.consecutive_frames = consecutive_frames
        self.history_length = history_length
        
        # EAR history per tracked face (keyed by face position hash)
        self._ear_history: dict = {}
        self._blink_counts: dict = {}
        self._closed_frames: dict = {}
        
        # Load face landmark detector
        self._landmark_detector = None
        self._init_landmark_detector()
    
    def _init_landmark_detector(self):
        """Initialize facial landmark detector."""
        try:
            # Use OpenCV's FaceDetectorYN with landmarks if available
            # Fallback: use simple contour-based eye detection
            cascade_path = cv2.data.haarcascades + 'haarcascade_eye.xml'
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
        3. EAR = minor_axis / major_axis
        
        Returns:
            EAR value (0.0-1.0) or None if can't compute
        """
        if eye_roi.size == 0:
            return None
        
        try:
            gray = cv2.cvtColor(eye_roi, cv2.COLOR_BGR2GRAY) if len(eye_roi.shape) == 3 else eye_roi
            gray = cv2.GaussianBlur(gray, (7, 7), 0)
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                return None
            
            # Get largest contour (the eye)
            largest = max(contours, key=cv2.contourArea)
            
            if len(largest) < 5:
                return None
            
            # Fit ellipse
            ellipse = cv2.fitEllipse(largest)
            (_, (major, minor), _) = ellipse
            
            if major == 0:
                return None
            
            ear = minor / major
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
            gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY) if len(face_roi.shape) == 3 else face_roi
            h, w = gray.shape[:2]
            
            # Only search upper half of face for eyes
            upper_half = gray[:h//2, :]
            
            eyes = self._eye_cascade.detectMultiScale(
                upper_half,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(20, 20)
            )
            
            eye_rois = []
            for (ex, ey, ew, eh) in eyes[:2]:  # Take first 2 eyes
                eye_roi = face_roi[ey:ey+eh, ex:ex+ew]
                if eye_roi.size > 0:
                    eye_rois.append(eye_roi)
            
            return eye_rois
        except Exception:
            return []
    
    def check_liveness(self, frame: np.ndarray, face_roi: np.ndarray, face_bbox: tuple) -> Tuple[bool, dict]:
        """
        Check if a face is live (real person) or spoof (photo/video).
        
        Args:
            frame: Full camera frame
            face_roi: Face region of interest
            face_bbox: Face bounding box (x, y, w, h)
            
        Returns:
            Tuple of (is_live, details_dict)
        """
        details = {
            "ear_values": [],
            "blink_count": 0,
            "avg_ear": 0.0,
            "method": "blink_detection"
        }
        
        if self._eye_cascade is None:
            # Liveness cannot be established — FAIL CLOSED. A photo or a
            # broken detector must never unlock the door.
            return False, {"method": "disabled", "reason": "eye cascade not loaded"}
        
        # Detect eyes
        eye_rois = self._detect_eyes(face_roi, face_bbox)
        
        if len(eye_rois) < 2:
            # Both eyes are required to compute a blink. A face with a
            # single visible eye (or none) cannot be proven live — deny.
            return False, {"method": "blink_detection", "reason": "insufficient_eyes", "eyes_found": len(eye_rois)}
        
        # Compute EAR for both eyes
        ears = []
        for eye_roi in eye_rois:
            ear = self._compute_ear(eye_roi)
            if ear is not None:
                ears.append(ear)
        
        if not ears:
            # EAR could not be computed — no evidence, fail closed.
            return False, {"method": "blink_detection", "reason": "ear_computation_failed"}
        
        avg_ear = sum(ears) / len(ears)
        
        # Track face by position hash (simple approach)
        x, y, w, h = face_bbox
        face_key = f"{x//50}_{y//50}"  # Quantize position for stability
        
        # Initialize tracking for new face
        if face_key not in self._ear_history:
            self._ear_history[face_key] = []
            self._blink_counts[face_key] = 0
            self._closed_frames[face_key] = 0
        
        # Add EAR to history
        history = self._ear_history[face_key]
        history.append(avg_ear)
        if len(history) > self.history_length:
            history.pop(0)
        
        # Detect blink: EAR drops below threshold for consecutive frames
        if avg_ear < self.ear_threshold:
            self._closed_frames[face_key] += 1
        else:
            if self._closed_frames[face_key] >= self.consecutive_frames:
                self._blink_counts[face_key] += 1
            self._closed_frames[face_key] = 0
        
        # Need at least 5 frames of history to make a determination.
        # Grace frames are ZERO: until positive liveness evidence exists,
        # no recognition is allowed.
        if len(history) < 5:
            return False, {
                "method": "blink_detection", 
                "reason": "collecting_baseline",
                "frames_collected": len(history),
                "blink_count": self._blink_counts[face_key],
                "avg_ear": round(avg_ear, 3)
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
            "frames_tracked": len(history)
        }
        
        return is_live, details
    
    def reset(self):
        """Reset all tracking state."""
        self._ear_history.clear()
        self._blink_counts.clear()
        self._closed_frames.clear()


# Global instance
liveness_detector = LivenessDetector()
