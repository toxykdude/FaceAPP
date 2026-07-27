"""
Access validation logic following SOPs.
"""
from typing import Optional, Tuple, Dict
from datetime import datetime, date
from loguru import logger

from api.backend_client import BackendAPIClient


class AccessValidator:
    """Validate access based on recognition results and membership rules."""
    
    def __init__(self):
        """Initialize access validator."""
        self.api_client = BackendAPIClient()
    
    async def _get_camera(self, camera_id: str) -> Optional[Dict]:
        """Get camera data from backend."""
        try:
            response = await self.api_client.client.get(
                f"{self.api_client.base_url}/cv/cameras"
            )
            if response.status_code == 200:
                cameras = response.json().get("cameras", [])
                for cam in cameras:
                    if cam["id"] == camera_id:
                        return cam
            return None
        except Exception:
            return None
    
    async def validate_access(
        self,
        member_id: Optional[str],
        confidence: float,
        camera_id: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate access for recognized face.
        
        Args:
            member_id: Recognized member ID (None if unknown)
            confidence: Recognition confidence score
            camera_id: Camera ID
            
        Returns:
            Tuple of (access_granted, denial_reason)
        """
        # Step 1: Check if face was matched
        if member_id is None:
            return False, "unknown_face"
        
        # Step 2: Check confidence threshold (already done in matcher, but double-check)
        # Note: Confidence threshold is already applied in template matching
        # This is a safety check
        if confidence < 0.70:
            return False, "low_confidence"
        
        # Step 3: Get member data
        member = await self.api_client.get_member(member_id)
        if not member:
            logger.error(f"Member {member_id} not found in database")
            return False, "member_not_found"
        
        # Step 4: Check member status
        if member["status"] != "active":
            return False, f"member_{member['status']}"
        
        # Step 5: Get active membership
        membership = await self.api_client.get_active_membership(member_id)
        if not membership:
            return False, "no_active_membership"
        
        # Step 6: Check membership status
        if membership["status"] == "expired":
            return False, "expired_membership"
        elif membership["status"] == "suspended":
            return False, "suspended_membership"
        elif membership["status"] != "active":
            return False, f"membership_{membership['status']}"
        
        # Step 7: Defense-in-depth date-window guard.
        # The backend (get_member_membership) is the source of truth and
        # already filters start_date<=today, but re-validate explicitly
        # here so display data (which may include a future-dated
        # membership) can never be mistaken for an access grant.
        try:
            membership_start = date.fromisoformat(membership.get("start_date", ""))
        except (TypeError, ValueError):
            membership_start = None

        if membership_start is not None and membership_start > date.today():
            return False, "membership_not_started"

        # Step 8: Check access rules
        access_rules = membership.get("access_rules", {})
        
        if access_rules:
            # Check day of week
            if "allowed_days" in access_rules and access_rules["allowed_days"]:
                current_day = datetime.now().strftime("%A").lower()
                if current_day not in access_rules["allowed_days"]:
                    return False, "access_day_restriction"
            
            # Check time windows
            if "time_windows" in access_rules and access_rules["time_windows"]:
                current_time = datetime.now().time()
                allowed = False
                
                for window in access_rules["time_windows"]:
                    start_time = datetime.strptime(window["start_time"], "%H:%M:%S").time()
                    end_time = datetime.strptime(window["end_time"], "%H:%M:%S").time()
                    
                    if start_time <= current_time <= end_time:
                        allowed = True
                        break
                
                if not allowed:
                    return False, "access_time_restriction"
            
            # Check location restrictions
            if "location_ids" in access_rules and access_rules["location_ids"]:
                camera_data = await self._get_camera(camera_id)
                if camera_data and camera_data.get("location"):
                    if camera_data["location"] not in access_rules["location_ids"]:
                        return False, "access_location_restriction"
        
        # All checks passed
        return True, None
    
    async def close(self):
        """Close API client."""
        await self.api_client.close()
