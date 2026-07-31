"""
Backend API client for CV service.

Communicates with the backend's /api/cv/ internal endpoints
using a shared secret (X-Internal-Secret header) for authentication.

Security note: the shared secret is REQUIRED. If INTERNAL_API_SECRET is
not configured the client refuses to construct, so requests can never be
sent unauthenticated. The secret and the biometric payloads it protects
must only travel over TLS in production: when REQUIRE_PROD_SECRETS is
enabled the client refuses to construct against a cleartext http://
BACKEND_API_URL. Error handling is split by severity:

- Auth/config failures (HTTP 401/403/503) RAISE RuntimeError. They are
  never masked as empty data, because treating a rejected/misconfigured
  secret as "no members enrolled" is a fail-open condition.
- Transient errors (httpx.RequestError: network blip, backend restart)
  and non-auth HTTP errors (e.g. 500) are LOGGED at ERROR and return the
  method's empty/None value. This is intentional: the critical caller
  (validation/access_validator.py) runs unguarded on every recognition,
  and returning None there fails SAFE (access is denied, the door stays
  closed) rather than crashing the recognition loop.

Hardening callers to distinguish "backend degraded" from "member absent"
is a tracked follow-up.
"""

import httpx
from typing import Optional, Dict, Any, List
from loguru import logger

from config import settings

# HTTP statuses that signal an authentication or configuration failure:
# 401/403 = rejected shared secret, 503 = backend secret misconfigured
# (see the sibling S1 backend change). These MUST propagate to callers
# and must never be swallowed into an empty/None return.
_AUTH_CONFIG_FAILURE_STATUSES = frozenset({401, 403, 503})


def _enforce_auth_config_ok(response: httpx.Response, operation: str) -> None:
    """Raise RuntimeError on auth/config failure statuses; no-op otherwise."""
    if response.status_code in _AUTH_CONFIG_FAILURE_STATUSES:
        raise RuntimeError(
            f"{operation}: backend returned HTTP "
            f"{response.status_code} (auth/config failure - verify "
            "INTERNAL_API_SECRET on the CV service and the backend)"
        )


class BackendAPIClient:
    """HTTP client for backend API."""

    def __init__(self):
        """Initialize API client. Requires INTERNAL_API_SECRET."""
        if not settings.INTERNAL_API_SECRET:
            raise RuntimeError(
                "INTERNAL_API_SECRET not configured; CV backend "
                "client cannot authenticate"
            )
        if settings.REQUIRE_PROD_SECRETS and settings.BACKEND_API_URL.startswith(
            "http://"
        ):
            raise RuntimeError(
                "REQUIRE_PROD_SECRETS is enabled and BACKEND_API_URL is "
                f"cleartext http:// ({settings.BACKEND_API_URL}) — the "
                "internal secret and biometric payloads must only travel "
                "over TLS in production; configure an https:// backend URL"
            )
        self.base_url = settings.BACKEND_API_URL
        self.timeout = settings.API_TIMEOUT
        self._headers = {
            "X-Internal-Secret": settings.INTERNAL_API_SECRET,
        }
        self.client = httpx.AsyncClient(
            timeout=self.timeout,
            headers=self._headers,
        )

    async def sync_templates(self) -> List[Dict[str, Any]]:
        """
        Fetch all enrolled member templates from backend.

        Returns:
            List of template dicts with embeddings and member metadata.

        Raises:
            RuntimeError: on auth/config failure (401/403/503).

        Transient/network errors and non-auth HTTP errors are logged at
        ERROR and return [] (fail-safe, non-fatal).
        """
        try:
            response = await self.client.get(f"{self.base_url}/cv/templates")
            _enforce_auth_config_ok(response, "sync_templates")
            response.raise_for_status()
            data = response.json()
            templates = data.get("templates", [])
            logger.info(f"Synced {len(templates)} templates from backend")
            return templates
        except httpx.HTTPStatusError:
            logger.error("sync_templates: unexpected HTTP error")
            return []
        except httpx.RequestError as e:
            logger.error(f"sync_templates: network error: {e}")
            return []

    async def get_member(self, member_id: str) -> Optional[Dict[str, Any]]:
        """
        Get member data.

        Returns None only when the member is genuinely absent (404).
        Auth/config failures (401/403/503) raise; transient/network and
        non-auth HTTP errors are logged at ERROR and return None
        (fail-safe, non-fatal).
        """
        try:
            response = await self.client.get(
                f"{self.base_url}/cv/members/{member_id}",
            )
            _enforce_auth_config_ok(response, f"get_member({member_id})")
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError:
            logger.error(f"get_member({member_id}): unexpected HTTP error")
            return None
        except httpx.RequestError as e:
            logger.error(f"get_member({member_id}): network error: {e}")
            return None

    async def get_active_membership(
        self,
        member_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get active membership for a member.

        Returns None on a genuine absence (404, or 200 with
        has_active falsy). Auth/config failures (401/403/503) raise;
        transient/network and non-auth HTTP errors are logged at ERROR
        and return None (fail-safe, non-fatal).
        """
        try:
            response = await self.client.get(
                f"{self.base_url}/cv/members/{member_id}/membership"
            )
            _enforce_auth_config_ok(
                response,
                f"get_active_membership({member_id})",
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()
            if data.get("has_active"):
                return data["membership"]
            return None
        except httpx.HTTPStatusError:
            logger.error(f"get_active_membership({member_id}): HTTP error")
            return None
        except httpx.RequestError as e:
            logger.error(f"get_active_membership({member_id}): network: {e}")
            return None

    async def get_cameras(self) -> List[Dict[str, Any]]:
        """
        Fetch all enabled cameras from the backend.

        This internal endpoint requires the X-Internal-Secret header,
        which the client attaches automatically at construction time.
        Auth/config failures (401/403/503) raise; transient/network and
        non-auth HTTP errors are logged at ERROR and return []
        (fail-safe, non-fatal).

        Returns:
            List of camera dicts with id, name, rtsp_url, fps, enabled.
        """
        try:
            response = await self.client.get(f"{self.base_url}/cv/cameras")
            _enforce_auth_config_ok(response, "get_cameras")
            response.raise_for_status()
            data = response.json()
            cameras = data.get("cameras", [])
            logger.info(f"Fetched {len(cameras)} cameras from backend")
            return cameras
        except httpx.HTTPStatusError:
            logger.error("get_cameras: unexpected HTTP error")
            return []
        except httpx.RequestError as e:
            logger.error(f"get_cameras: network error: {e}")
            return []

    async def create_access_event(
        self,
        camera_id: str,
        member_id: Optional[str],
        confidence_score: Optional[float],
        access_granted: bool,
        denial_reason: Optional[str] = None,
        frame_snapshot_path: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Create an access event in the backend (audit record).

        Auth/config failures (401/403/503) raise — silently succeeding
        on a rejected/misconfigured secret would mask a broken audit
        path. Transient/network and non-auth HTTP errors are logged at
        ERROR and return None (fail-safe, non-fatal).
        """
        try:
            response = await self.client.post(
                f"{self.base_url}/events",
                json={
                    "camera_id": camera_id,
                    "member_id": member_id,
                    "confidence_score": confidence_score,
                    "access_granted": access_granted,
                    "denial_reason": denial_reason,
                    "frame_snapshot_path": frame_snapshot_path,
                },
            )
            _enforce_auth_config_ok(response, "create_access_event")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError:
            logger.error("create_access_event: unexpected HTTP error")
            return None
        except httpx.RequestError as e:
            logger.error(f"create_access_event: network error: {e}")
            return None

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
