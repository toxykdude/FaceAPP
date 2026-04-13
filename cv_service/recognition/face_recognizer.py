"""
Face recognition module using FaceNet.
"""
import torch
import numpy as np
from facenet_pytorch import InceptionResnetV1
from PIL import Image
import cv2
from typing import Optional, Tuple

from config import settings


class FaceRecognizer:
    """Face recognition using FaceNet."""
    
    def __init__(self):
        """Initialize face recognizer."""
        self.device = torch.device('cuda:0' if settings.USE_GPU and torch.cuda.is_available() else 'cpu')
        
        # Load pretrained FaceNet model
        self.model = InceptionResnetV1(pretrained='vggface2').eval().to(self.device)
    
    def generate_embedding(self, face_roi: np.ndarray) -> np.ndarray:
        """
        Generate face embedding (512-dimensional vector).
        
        Args:
            face_roi: Face region of interest (BGR image)
            
        Returns:
            Face embedding as numpy array
        """
        # Preprocess face
        face_tensor = self._preprocess_face(face_roi)
        
        # Generate embedding
        with torch.no_grad():
            embedding = self.model(face_tensor)
        
        # Convert to numpy and normalize
        embedding_np = embedding.cpu().numpy().flatten()
        embedding_np = embedding_np / np.linalg.norm(embedding_np)
        
        return embedding_np
    
    def _preprocess_face(self, face_roi: np.ndarray) -> torch.Tensor:
        """
        Preprocess face for FaceNet.
        
        Args:
            face_roi: Face ROI (BGR image)
            
        Returns:
            Preprocessed face tensor
        """
        # Convert BGR to RGB
        face_rgb = cv2.cvtColor(face_roi, cv2.COLOR_BGR2RGB)
        
        # Resize to 160x160 (FaceNet input size)
        face_resized = cv2.resize(face_rgb, (160, 160))
        
        # Convert to PIL Image
        face_pil = Image.fromarray(face_resized)
        
        # Convert to tensor and normalize
        face_tensor = torch.from_numpy(np.array(face_pil)).float()
        face_tensor = face_tensor.permute(2, 0, 1)  # HWC to CHW
        face_tensor = (face_tensor - 127.5) / 128.0  # Normalize to [-1, 1]
        face_tensor = face_tensor.unsqueeze(0)  # Add batch dimension
        
        return face_tensor.to(self.device)
    
    @staticmethod
    def calculate_similarity(embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Calculate cosine similarity between two embeddings.
        
        Args:
            embedding1: First embedding
            embedding2: Second embedding
            
        Returns:
            Similarity score (0.0 to 1.0)
        """
        # Cosine similarity
        similarity = np.dot(embedding1, embedding2) / (
            np.linalg.norm(embedding1) * np.linalg.norm(embedding2)
        )
        
        # Convert to 0-1 range
        similarity = (similarity + 1) / 2
        
        return float(similarity)
    
    def match_embedding(self, query_embedding: np.ndarray, stored_embedding: np.ndarray) -> Tuple[bool, float]:
        """
        Match query embedding against stored embedding.
        
        Args:
            query_embedding: Query face embedding
            stored_embedding: Stored face embedding
            
        Returns:
            Tuple of (is_match, confidence_score)
        """
        similarity = self.calculate_similarity(query_embedding, stored_embedding)
        is_match = similarity >= settings.CONFIDENCE_THRESHOLD
        
        return is_match, similarity
