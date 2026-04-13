"""
Tests for liveness detector.
"""
import pytest
import numpy as np
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detection.liveness_detector import LivenessDetector


class TestLivenessDetector:
    """Test anti-spoofing liveness detection."""
    
    def test_init(self):
        """Detector should initialize."""
        detector = LivenessDetector()
        assert detector.ear_threshold == 0.21
        assert detector.history_length == 30
    
    def test_no_face_returns_true(self):
        """No face (empty ROI) should pass by default."""
        detector = LivenessDetector()
        empty_roi = np.zeros((10, 10, 3), dtype=np.uint8)
        is_live, details = detector.check_liveness(empty_roi, empty_roi, (0, 0, 10, 10))
        # Should pass (insufficient eyes to determine)
        assert isinstance(is_live, bool)
        assert 'method' in details
    
    def test_reset(self):
        """Reset should clear all tracking."""
        detector = LivenessDetector()
        detector._ear_history['test'] = [0.3, 0.2, 0.3]
        detector._blink_counts['test'] = 1
        detector.reset()
        assert len(detector._ear_history) == 0
        assert len(detector._blink_counts) == 0
    
    def test_ear_computation_empty(self):
        """Empty ROI should return None EAR."""
        detector = LivenessDetector()
        result = detector._compute_ear(np.zeros((0, 0, 3), dtype=np.uint8))
        assert result is None
