"""
Template matching engine for face recognition.
"""
import numpy as np
from typing import Optional, Tuple, List
from loguru import logger

from recognition.face_recognizer import FaceRecognizer
from recognition.template_cache import TemplateCache
from config import settings


class TemplateMatcher:
    """Match face embeddings against cached member templates."""
    
    def __init__(self):
        """Initialize template matcher."""
        self.recognizer = FaceRecognizer()
        self.cache = TemplateCache()
    
    def find_match(self, query_embedding: np.ndarray) -> Tuple[Optional[str], float, Optional[dict]]:
        """
        Find matching member for query embedding.
        
        Args:
            query_embedding: Face embedding to match
            
        Returns:
            Tuple of (member_id, confidence_score, member_data) or (None, 0.0, None) if no match
        """
        # Get all active templates from cache
        cached_templates = self.cache.get_all_active_templates()
        
        if not cached_templates:
            logger.warning("No templates in cache")
            return None, 0.0, None
        
        # Calculate similarities
        matches = []
        for template_data in cached_templates:
            stored_embedding = template_data["template"]
            similarity = self.recognizer.calculate_similarity(query_embedding, stored_embedding)
            
            matches.append({
                "member_id": template_data["member_id"],
                "similarity": similarity,
                "name": template_data["name"],
                "status": template_data["status"],
                "membership_status": template_data.get("membership_status")
            })
        
        # Sort by similarity (descending)
        matches.sort(key=lambda x: x["similarity"], reverse=True)
        
        # Get best match
        best_match = matches[0]
        
        # Check if above threshold
        if best_match["similarity"] >= settings.CONFIDENCE_THRESHOLD:
            logger.info(
                f"Match found: {best_match['name']} "
                f"(confidence: {best_match['similarity']:.2f})"
            )
            
            # Refresh cache TTL for matched member
            self.cache.refresh_template(best_match["member_id"])
            
            return (
                best_match["member_id"],
                best_match["similarity"],
                {
                    "name": best_match["name"],
                    "status": best_match["status"],
                    "membership_status": best_match["membership_status"]
                }
            )
        else:
            logger.info(
                f"No match above threshold. Best: {best_match['name']} "
                f"(confidence: {best_match['similarity']:.2f})"
            )
            return None, best_match["similarity"], None
    
    def match_against_specific(
        self,
        query_embedding: np.ndarray,
        member_id: str
    ) -> Tuple[bool, float]:
        """
        Match query embedding against specific member.
        
        Args:
            query_embedding: Face embedding to match
            member_id: Specific member ID to match against
            
        Returns:
            Tuple of (is_match, confidence_score)
        """
        # Get template from cache
        template_data = self.cache.get_template(member_id)
        
        if not template_data:
            logger.warning(f"Template not found in cache for member {member_id}")
            return False, 0.0
        
        stored_embedding = template_data["template"]
        similarity = self.recognizer.calculate_similarity(query_embedding, stored_embedding)
        
        is_match = similarity >= settings.CONFIDENCE_THRESHOLD
        
        return is_match, similarity
