"""
Face quality assessment module.
"""
import cv2
import numpy as np
from typing import Tuple


class FaceQualityAssessor:
    """Assess face quality for enrollment and recognition."""
    
    @staticmethod
    def assess_quality(face_roi: np.ndarray) -> Tuple[float, dict]:
        """
        Assess face quality.
        
        Args:
            face_roi: Face region of interest
            
        Returns:
            Tuple of (quality_score, metrics_dict)
        """
        metrics = {}
        
        # 1. Sharpness (Laplacian variance)
        gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        sharpness = min(laplacian_var / 500.0, 1.0)  # Normalize
        metrics['sharpness'] = sharpness
        
        # 2. Brightness (mean pixel value)
        mean_brightness = gray.mean()
        # Ideal range: 80-180
        if 80 <= mean_brightness <= 180:
            brightness = 1.0
        elif mean_brightness < 80:
            brightness = mean_brightness / 80.0
        else:
            brightness = 1.0 - ((mean_brightness - 180) / 75.0)
        brightness = max(0.0, min(1.0, brightness))
        metrics['brightness'] = brightness
        metrics['mean_brightness'] = mean_brightness
        
        # 3. Contrast (standard deviation)
        contrast_std = gray.std()
        contrast = min(contrast_std / 50.0, 1.0)  # Normalize
        metrics['contrast'] = contrast
        
        # 4. Face size
        face_area = face_roi.shape[0] * face_roi.shape[1]
        # Prefer larger faces (better resolution)
        size_score = min(face_area / (200 * 200), 1.0)
        metrics['size_score'] = size_score
        
        # Calculate overall quality score (weighted average)
        quality_score = (
            sharpness * 0.4 +
            brightness * 0.3 +
            contrast * 0.2 +
            size_score * 0.1
        )
        
        metrics['quality_score'] = quality_score
        
        return quality_score, metrics
    
    @staticmethod
    def get_quality_feedback(metrics: dict) -> str:
        """
        Get human-readable quality feedback.
        
        Args:
            metrics: Quality metrics dictionary
            
        Returns:
            Feedback message
        """
        feedback = []
        
        if metrics['sharpness'] < 0.5:
            feedback.append("Hold still - image is blurry")
        
        if metrics['mean_brightness'] < 80:
            feedback.append("Improve lighting - too dark")
        elif metrics['mean_brightness'] > 180:
            feedback.append("Reduce lighting - too bright")
        
        if metrics['contrast'] < 0.4:
            feedback.append("Improve contrast - adjust lighting")
        
        if metrics['size_score'] < 0.5:
            feedback.append("Move closer to camera")
        
        if not feedback:
            return "Quality good - ready to capture"
        
        return " | ".join(feedback)
