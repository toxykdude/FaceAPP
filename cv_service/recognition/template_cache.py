"""
Redis cache manager for member templates.
"""
import redis
import json
import numpy as np
from typing import Optional, Dict, List
from loguru import logger

from config import settings


class TemplateCache:
    """Redis cache for member face templates."""
    
    def __init__(self):
        """Initialize Redis connection."""
        self.redis_client = redis.from_url(settings.REDIS_URL, decode_responses=False)
        self.ttl = settings.CACHE_TTL
    
    def store_template(self, member_id: str, template: np.ndarray, member_data: dict):
        """
        Store member template in cache.
        
        Args:
            member_id: Member UUID
            template: Face embedding (numpy array)
            member_data: Member metadata (name, status, etc.)
        """
        key = f"member:template:{member_id}"
        
        # Serialize template and data
        data = {
            "template": template.tolist(),
            "member_id": member_id,
            "name": member_data.get("name"),
            "status": member_data.get("status"),
            "membership_status": member_data.get("membership_status")
        }
        
        # Store in Redis
        self.redis_client.setex(
            key,
            self.ttl,
            json.dumps(data)
        )
        
        logger.debug(f"Cached template for member {member_id}")
    
    def get_template(self, member_id: str) -> Optional[Dict]:
        """
        Get member template from cache.
        
        Args:
            member_id: Member UUID
            
        Returns:
            Dict with template and metadata, or None if not found
        """
        key = f"member:template:{member_id}"
        
        data = self.redis_client.get(key)
        if not data:
            return None
        
        # Deserialize
        cached_data = json.loads(data)
        
        # Convert template back to numpy array
        cached_data["template"] = np.array(cached_data["template"])
        
        return cached_data
    
    def get_all_active_templates(self) -> List[Dict]:
        """
        Get all active member templates from cache.
        
        Returns:
            List of dicts with templates and metadata
        """
        # Get all template keys
        pattern = "member:template:*"
        keys = self.redis_client.keys(pattern)
        
        templates = []
        for key in keys:
            data = self.redis_client.get(key)
            if data:
                cached_data = json.loads(data)
                
                # Only include active members
                if cached_data.get("status") == "active":
                    cached_data["template"] = np.array(cached_data["template"])
                    templates.append(cached_data)
        
        logger.debug(f"Retrieved {len(templates)} active templates from cache")
        return templates
    
    def remove_template(self, member_id: str):
        """
        Remove member template from cache.
        
        Args:
            member_id: Member UUID
        """
        key = f"member:template:{member_id}"
        self.redis_client.delete(key)
        logger.debug(f"Removed template for member {member_id}")
    
    def clear_all_templates(self):
        """Clear all member templates from cache."""
        pattern = "member:template:*"
        keys = self.redis_client.keys(pattern)
        
        if keys:
            self.redis_client.delete(*keys)
            logger.info(f"Cleared {len(keys)} templates from cache")
    
    def refresh_template(self, member_id: str):
        """
        Refresh TTL for a member template.
        
        Args:
            member_id: Member UUID
        """
        key = f"member:template:{member_id}"
        self.redis_client.expire(key, self.ttl)
    
    def ping(self) -> bool:
        """
        Test Redis connection.
        
        Returns:
            True if connected, False otherwise
        """
        try:
            self.redis_client.ping()
            return True
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            return False
