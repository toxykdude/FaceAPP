"""
Redis cache manager for member templates.
"""
import base64
import json
import numpy as np
import redis
from typing import Optional, Dict, List
from loguru import logger

from config import settings
from core.encryption import decrypt_biometric_data, encrypt_biometric_data


class TemplateCache:
    """Redis cache for member face templates.

    Templates are biometric data (Colombia Ley 1581/2012, GDPR Art. 9), so
    when ENCRYPTION_KEY is configured the entire serialized record is
    encrypted with AES-256-GCM before it reaches Redis and decrypted on
    read. Without a key the cache falls back to cleartext for development,
    but refuses to start when REQUIRE_PROD_SECRETS is enabled.
    """

    def __init__(self):
        """Initialize Redis connection."""
        if not settings.ENCRYPTION_KEY:
            if settings.REQUIRE_PROD_SECRETS:
                raise RuntimeError(
                    "ENCRYPTION_KEY not configured and REQUIRE_PROD_SECRETS is "
                    "enabled — refusing to cache biometric templates in cleartext"
                )
            logger.warning(
                "ENCRYPTION_KEY not configured — member templates are cached in "
                "CLEARTEXT in Redis (development only). Set ENCRYPTION_KEY in "
                "production."
            )
        self.redis_client = redis.from_url(settings.REDIS_URL, decode_responses=False)
        self.ttl = settings.CACHE_TTL

    @property
    def _version(self):
        """Read current cache version from Redis on every access.

        This ensures all TemplateCache instances (including long-lived ones
        in RTSPStreamProcessor threads) always read the latest version,
        preventing stale version references after periodic refreshes.
        """
        return int(self.redis_client.get("template_cache:version") or 0)
    
    def increment_version(self):
        """Increment cache version for atomic reloads."""
        self.redis_client.incr("template_cache:version")
    
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
    
    def _serialize(self, data: dict) -> str:
        """Serialize a template record, encrypting it when a key is set.

        The whole record (embedding + metadata) is encrypted with
        AES-256-GCM and base64-encoded inside a JSON envelope, so no
        biometric bytes ever sit in cleartext in Redis.
        """
        if settings.ENCRYPTION_KEY:
            encrypted = encrypt_biometric_data(
                json.dumps(data).encode("utf-8")
            )
            return json.dumps(
                {
                    "encrypted": True,
                    "payload": base64.b64encode(encrypted).decode("ascii"),
                }
            )
        return json.dumps(data)

    def _deserialize(self, raw) -> Optional[Dict]:
        """Parse a cached record, decrypting it when the envelope requires.

        Legacy plaintext records written before ENCRYPTION_KEY was enabled
        are still served (with a loud warning) so recognition keeps working
        during rollout — they are replaced on the next template reload.

        Returns None when the record cannot be parsed or decrypted.
        """
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            logger.error("Template cache entry is not valid JSON — ignoring")
            return None

        if isinstance(parsed, dict) and parsed.get("encrypted") is True:
            if not settings.ENCRYPTION_KEY:
                logger.error(
                    "Template cache entry is encrypted but ENCRYPTION_KEY is not "
                    "configured — cannot read it"
                )
                return None
            try:
                blob = base64.b64decode(parsed["payload"])
                decrypted = decrypt_biometric_data(blob)
                return json.loads(decrypted.decode("utf-8"))
            except Exception as e:
                logger.error(f"Failed to decrypt template cache entry: {e}")
                return None

        if settings.ENCRYPTION_KEY:
            logger.warning(
                "Read legacy cleartext template cache entry — written before "
                "ENCRYPTION_KEY was enabled; it will be re-encrypted on the "
                "next template reload"
            )
        return parsed

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
            "membership_status": member_data.get("membership_status"),
            "membership_end_date": member_data.get("membership_end_date")
        }
        
        # Store in Redis (encrypted at rest when ENCRYPTION_KEY is set)
        self.redis_client.setex(
            key,
            self.ttl,
            self._serialize(data)
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
        
        # Deserialize (and decrypt when the record is encrypted)
        cached_data = self._deserialize(data)
        if cached_data is None:
            return None
        
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
                cached_data = self._deserialize(data)
                if cached_data is None:
                    continue
                
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

    REVOKED_SET_KEY = "cv:revoked"
    REVOKED_MARKER_TTL = 60

    def revoke_member(self, member_id: str):
        """Mark a member as revoked for a bounded 60-second window.

        The marker set is the generation check for the reload/invalidate
        race: a template reload that read the backend snapshot BEFORE a
        member delete committed will still see this marker when it stores
        AFTER the invalidate removed the member, and skip it. No lock is
        needed — the marker outlives the delete → invalidate window, and it
        expires so normal future reloads are unaffected. The set TTL is
        refreshed on each add.
        """
        self.redis_client.sadd(self.REVOKED_SET_KEY, member_id)
        self.redis_client.expire(self.REVOKED_SET_KEY, self.REVOKED_MARKER_TTL)

    def is_revoked(self, member_id: str) -> bool:
        """True while the member carries an active revocation marker."""
        return bool(
            self.redis_client.sismember(self.REVOKED_SET_KEY, member_id)
        )

    def clear_all_templates(self):
        """Clear all member templates from current and old versions."""
        # Clear all versions (0..current)
        current_v = self._version
        for v in range(current_v + 1):
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
