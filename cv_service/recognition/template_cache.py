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
        # Shared version stored in Redis so all instances stay in sync
        self._version = int(self.redis_client.get("template_cache:version") or 0)
    
    def increment_version(self):
        """Increment cache version for atomic reloads."""
        self._version = self.redis_client.incr("template_cache:version")
    
    def _make_key(self, member_id: str) -> str:
        """Build versioned cache key."""
        return f"member:template:v{self._version}:{member_id}"
    
    def _scan_keys(self, pattern: str) -> list:
        """SCAN-based key retrieval (non-blocking alternative to KEYS)."""
        keys = []
        cursor = 0
        while True:
            cursor, batch = self.redis_client.scan(cursor, match=pattern, count=100)
            keys.extend(batch)
            if cursor == 0:
                break
        return keys
    
    def store_template(self, member_id: str, template: np.ndarray, member_data: dict):
        """
        Store member template in cache.
        
        Args:
            member_id: Member UUID
            template: Face embedding (numpy array)
            member_data: Member metadata (name, status, etc.)
        """
        key = self._make_key(member_id)
        
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
        key = self._make_key(member_id)
        
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
        # Get all template keys for current version
        pattern = f"member:template:v{self._version}:*"
        keys = self._scan_keys(pattern)
        
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
        key = self._make_key(member_id)
        self.redis_client.delete(key)
        logger.debug(f"Removed template for member {member_id}")
    
    def clear_all_templates(self):
        """Clear all member templates from current and old versions."""
        # Clear all versions (0..current)
        for v in range(self._version + 1):
            pattern = f"member:template:v{v}:*"
            keys = self._scan_keys(pattern)
            if keys:
                self.redis_client.delete(*keys)
        # Also clean unversioned keys (legacy)
        keys = []
        cursor = 0
        while True:
            cursor, batch = self.redis_client.scan(cursor, match="member:template:*", count=100)
            # Only delete keys that don't have :v in them
            unversioned = [k for k in batch if b":v" not in k]
            keys.extend(unversioned)
            if cursor == 0:
                break
        if keys:
            self.redis_client.delete(*keys)
        logger.info("Cleared all templates from cache")
    
    def refresh_template(self, member_id: str):
        """
        Refresh TTL for a member template.
        
        Args:
            member_id: Member UUID
        """
        key = self._make_key(member_id)
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
