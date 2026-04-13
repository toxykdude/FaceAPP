"""
Face detection module using MTCNN or Haar Cascade.
"""
import cv2
import numpy as np
from typing import Optional, List, Tuple
from facenet_pytorch import MTCNN
import torch

from config import settings


class FaceDetector:
    """Face detection using MTCNN or Haar Cascade."""
    
    def __init__(self):
        """Initialize face detector."""
        self.model_type = settings.FACE_DETECTION_MODEL
        self.device = torch.device('cuda:0' if settings.USE_GPU and torch.cuda.is_available() else 'cpu')
        
        if self.model_type == "mtcnn":
            self.detector = MTCNN(
                keep_all=True,
                device=self.device,
                min_face_size=settings.MIN_FACE_SIZE
            )
        else:  # haar
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            self.detector = cv2.CascadeClassifier(cascade_path)
    
    def detect_faces(self, frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """
        Detect faces in frame.
        
        Args:
            frame: BGR image from OpenCV
            
        Returns:
            List of face bounding boxes [(x, y, w, h), ...]
        """
        if self.model_type == "mtcnn":
            return self._detect_mtcnn(frame)
        else:
            return self._detect_haar(frame)
    
    def _detect_mtcnn(self, frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """Detect faces using MTCNN."""
        # Convert BGR to RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Detect faces
        boxes, probs = self.detector.detect(rgb_frame)
        
        if boxes is None:
            return []
        
        # Convert to (x, y, w, h) format
        faces = []
        for box in boxes:
            x1, y1, x2, y2 = box.astype(int)
            x, y = x1, y1
            w, h = x2 - x1, y2 - y1
            
            # Filter by minimum size
            if w >= settings.MIN_FACE_SIZE and h >= settings.MIN_FACE_SIZE:
                faces.append((x, y, w, h))
        
        return faces
    
    def _detect_haar(self, frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """Detect faces using Haar Cascade."""
        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Equalize histogram for better detection
        gray = cv2.equalizeHist(gray)
        
        # Detect faces
        faces = self.detector.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(settings.MIN_FACE_SIZE, settings.MIN_FACE_SIZE)
        )
        
        # Convert to list of tuples
        return [(int(x), int(y), int(w), int(h)) for x, y, w, h in faces]
    
    def get_largest_face(self, faces: List[Tuple[int, int, int, int]]) -> Optional[Tuple[int, int, int, int]]:
        """
        Get the largest face from detected faces.
        
        Args:
            faces: List of face bounding boxes
            
        Returns:
            Largest face bounding box or None
        """
        if not faces:
            return None
        
        # Sort by area (w * h) descending
        faces_sorted = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
        return faces_sorted[0]
    
    def extract_face_roi(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> np.ndarray:
        """
        Extract face region of interest from frame.
        
        Args:
            frame: Full frame
            bbox: Face bounding box (x, y, w, h)
            
        Returns:
            Face ROI
        """
        x, y, w, h = bbox
        
        # Add padding (10%)
        padding = int(min(w, h) * 0.1)
        x1 = max(0, x - padding)
        y1 = max(0, y - padding)
        x2 = min(frame.shape[1], x + w + padding)
        y2 = min(frame.shape[0], y + h + padding)
        
        return frame[y1:y2, x1:x2]
