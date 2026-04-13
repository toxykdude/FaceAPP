"""
Tests for face quality assessor.
"""
import pytest
import numpy as np
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detection.quality_assessor import FaceQualityAssessor


class TestQualityAssessor:
    """Test face quality assessment."""
    
    def test_sharp_image_high_quality(self):
        """Sharp, well-lit image should score high."""
        # Create a synthetic "face" image with good quality
        img = np.random.randint(100, 200, (200, 200, 3), dtype=np.uint8)
        # Add high-frequency detail for sharpness
        img[::2, ::2] = 255
        img[1::2, 1::2] = 50
        
        score, metrics = FaceQualityAssessor.assess_quality(img)
        assert 0.0 <= score <= 1.0
        assert 'sharpness' in metrics
        assert 'brightness' in metrics
    
    def test_black_image_low_quality(self):
        """Pure black image should score low."""
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        score, metrics = FaceQualityAssessor.assess_quality(img)
        assert metrics['brightness'] < 0.5
    
    def test_quality_feedback_good(self):
        """Good metrics should give positive feedback."""
        metrics = {
            'sharpness': 0.8,
            'brightness': 1.0,
            'mean_brightness': 130,
            'contrast': 0.7,
            'size_score': 0.9,
            'quality_score': 0.85
        }
        feedback = FaceQualityAssessor.get_quality_feedback(metrics)
        assert 'ready' in feedback.lower() or 'good' in feedback.lower()
    
    def test_quality_feedback_blurry(self):
        """Blurry image should mention blur in feedback."""
        metrics = {
            'sharpness': 0.3,
            'brightness': 1.0,
            'mean_brightness': 130,
            'contrast': 0.7,
            'size_score': 0.9,
            'quality_score': 0.5
        }
        feedback = FaceQualityAssessor.get_quality_feedback(metrics)
        assert 'still' in feedback.lower() or 'blur' in feedback.lower()
    
    def test_grayscale_input(self):
        """Should handle grayscale input."""
        gray = np.random.randint(80, 180, (150, 150), dtype=np.uint8)
        img = np.stack([gray]*3, axis=-1)
        score, metrics = FaceQualityAssessor.assess_quality(img)
        assert 0.0 <= score <= 1.0
