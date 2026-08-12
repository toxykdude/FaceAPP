"""
Template matching engine for face recognition.
"""
import numpy as np
from collections import Counter
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
        # Memoized decrypted template set, keyed by the cache snapshot token.
        self._snapshot_token: Optional[tuple] = None
        self._matrix: Optional[np.ndarray] = None
        self._meta: List[dict] = []

    def _load_snapshot(self) -> Tuple[Optional[np.ndarray], List[dict]]:
        """Return the L2-normalized template matrix, rebuilding only on change.

        Reading and decrypting every template per frame cost ~213 ms for 540
        members (of which only ~4 ms was similarity math) and ran on the
        asyncio event loop, which starved the kiosk WebSocket of its ping
        deadline and dropped the connection. The token is a single MGET, so
        an unchanged cache costs one round trip instead of 540 plus 540
        AES-GCM decryptions.
        """
        token = self.cache.snapshot_token()
        if token == self._snapshot_token and self._matrix is not None:
            return self._matrix, self._meta

        cached_templates = self.cache.get_all_active_templates()
        if not cached_templates:
            # Do NOT memoize an empty result: it usually means a reload is in
            # flight, and caching it would extend a momentary gap.
            self._snapshot_token = None
            self._matrix = None
            self._meta = []
            return None, []

        vectors = [
            np.asarray(t["template"], dtype=np.float32).ravel()
            for t in cached_templates
        ]
        # Every template must share the embedding width to be stacked. Drop
        # the odd ones out instead of raising: a single malformed record must
        # cost one member their match, not take recognition down for everyone.
        width = Counter(v.shape[0] for v in vectors).most_common(1)[0][0]
        usable = [
            (vector, t)
            for vector, t in zip(vectors, cached_templates)
            if vector.shape[0] == width
        ]
        if len(usable) != len(vectors):
            logger.error(
                f"Skipped {len(vectors) - len(usable)} template(s) whose "
                f"embedding width is not {width}"
            )

        matrix = np.stack([vector for vector, _ in usable])
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        # A zero-norm template would divide by zero and poison every score.
        norms[norms == 0] = 1.0

        self._matrix = matrix / norms
        self._meta = [
            {
                "member_id": t["member_id"],
                "name": t["name"],
                "status": t["status"],
                "membership_status": t.get("membership_status"),
                "membership_end_date": t.get("membership_end_date"),
            }
            for _, t in usable
        ]
        self._snapshot_token = token
        logger.info(f"Template snapshot rebuilt: {len(self._meta)} templates")
        return self._matrix, self._meta

    def find_match(self, query_embedding: np.ndarray) -> Tuple[Optional[str], float, Optional[dict]]:
        """
        Find matching member for query embedding.

        Args:
            query_embedding: Face embedding to match

        Returns:
            Tuple of (member_id, confidence_score, member_data) or (None, 0.0, None) if no match
        """
        matrix, meta = self._load_snapshot()

        if matrix is None:
            logger.warning("No templates in cache")
            return None, 0.0, None

        query = np.asarray(query_embedding, dtype=np.float32).ravel()
        query_norm = np.linalg.norm(query)
        if query_norm == 0:
            logger.warning("Query embedding has zero norm — cannot match")
            return None, 0.0, None

        # Same score as FaceRecognizer.calculate_similarity — cosine mapped
        # from [-1, 1] to [0, 1] — but batched over every template at once.
        # It is compared against CONFIDENCE_THRESHOLD, so the mapping must
        # stay identical or the accept/reject boundary silently moves.
        similarities = (matrix @ (query / query_norm) + 1.0) / 2.0

        best_index = int(np.argmax(similarities))
        best_match = dict(meta[best_index])
        best_match["similarity"] = float(similarities[best_index])

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
                    "membership_status": best_match["membership_status"],
                    "membership_end_date": best_match.get("membership_end_date")
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
