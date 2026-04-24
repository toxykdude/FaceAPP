"""
Backend API client for CV service.

Communicates with the backend's /api/cv/ internal endpoints
using a shared secret (X-Internal-Secret header) for authentication.
"""
import httpx
from typing import Optional, Dict, Any, List
from loguru import logger

from config import settings


class BackendAPIClient:
    """HTTP client for backend API."""
    
    def __init__(self):
        """Initialize API client."""
        self.base_url = settings.BACKEND_API_URL
        self.timeout = settings.API_TIMEOUT
        self._headers = {}
        if settings.INTERNAL_API_SECRET:
            self._headers["X-Internal-Secret"] = settings.INTERNAL_API_SECRET
        self.client = httpx.AsyncClient(timeout=self.timeout, headers=self._headers)
    
    async def sync_templates(self) -> List[Dict[str, Any]]:
        """
        Fetch all enrolled member templates from backend.
        
        Returns:
            List of template dicts with embeddings and member metadata.
        """
        try:
            response = await self.client.get(f"{self.base_url}/cv/templates")
            response.raise_for_status()
            data = response.json()
            templates = data.get("templates", [])
            logger.info(f"Synced {len(templates)} templates from backend")
            return templates
        except Exception as e:
            logger.error(f"Failed to sync templates: {e}")
            return []
    
    async def get_member(self, member_id: str) -> Optional[Dict[str, Any]]:
        """Get member data."""
        try:
            response = await self.client.get(f"{self.base_url}/cv/members/{member_id}")
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get member {member_id}: {e}")
            return None
    
    async def get_active_membership(self, member_id: str) -> Optional[Dict[str, Any]]:
        """Get active membership for a member."""
        try:
            response = await self.client.get(f"{self.base_url}/cv/members/{member_id}/membership")
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()
            if data.get("has_active"):
                return data["membership"]
            return None
        except Exception as e:
            logger.error(f"Failed to get membership for {member_id}: {e}")
            return None
    
    async def get_cameras(self) -> List[Dict[str, Any]]:
        """
        Fetch all enabled cameras from backend (internal endpoint, no auth).
        
        Returns:
            List of camera dicts with id, name, rtsp_url, fps, enabled.
        """
        try:
            response = await self.client.get(f"{self.base_url}/cv/cameras")
            if response.status_code == 200:
                data = response.json()
                cameras = data.get("cameras", [])
                logger.info(f"Fetched {len(cameras)} cameras from backend")
                return cameras
            return []
        except Exception as e:
            logger.error(f"Failed to fetch cameras: {e}")
            return []
    
    async def create_access_event(
        self,
        camera_id: str,
        member_id: Optional[str],
        confidence_score: Optional[float],
        access_granted: bool,
        denial_reason: Optional[str] = None,
        frame_snapshot_path: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Create access event in backend."""
        try:
            response = await self.client.post(
                f"{self.base_url}/events",
                json={
                    "camera_id": camera_id,
                    "member_id": member_id,
                    "confidence_score": confidence_score,
                    "access_granted": access_granted,
                    "denial_reason": denial_reason,
                    "frame_snapshot_path": frame_snapshot_path
                }
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to create access event: {e}")
            return None
    
    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
