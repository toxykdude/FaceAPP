"""
HTTP client for the FaceAPP backend's WiFi endpoints.

Thin sync wrapper (the pyrad server is a threaded/blocking process) around:

  POST {BACKEND_API_URL}/wifi/authorize    -> decision dict
  POST {BACKEND_API_URL}/wifi/accounting   -> ack

Auth is the backend's X-Internal-Secret (same trust domain as the CV
service). Authorization failures RAISE — the RADIUS layer fails closed on
them (Access-Reject). Accounting failures are returned as False and logged
by the caller: accounting is telemetry, authorization is the boundary.
"""

import logging
from typing import Any, Dict, Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)


class BackendError(Exception):
    """Backend unreachable or returned a server error (fail closed → reject)."""


class BackendAuthError(BackendError):
    """401/403/503 from the backend — the shared secret is misconfigured."""


class BackendClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        secret: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.base_url = (base_url or settings.BACKEND_API_URL).rstrip("/")
        self._client = httpx.Client(
            timeout=timeout or settings.BACKEND_TIMEOUT_SECONDS,
            headers={"X-Internal-Secret": secret or settings.INTERNAL_API_SECRET},
        )

    def authorize(
        self,
        document: str,
        client_mac: Optional[str] = None,
        client_ip: Optional[str] = None,
        nas_ip: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Ask the backend whether ``document`` may use the member WiFi.

        Raises BackendError/BackendAuthError — never returns a fallback
        decision, so the caller can fail closed deterministically.
        """
        try:
            response = self._client.post(
                f"{self.base_url}/wifi/authorize",
                json={
                    "document": document,
                    "client_mac": client_mac,
                    "client_ip": client_ip,
                    "nas_ip": nas_ip,
                },
            )
        except httpx.HTTPError as exc:
            raise BackendError(f"backend unreachable: {exc}") from exc

        if response.status_code in (401, 403, 503):
            raise BackendAuthError(
                f"backend rejected internal credentials (HTTP {response.status_code})"
            )
        if response.status_code >= 500:
            raise BackendError(f"backend server error HTTP {response.status_code}")
        if response.status_code != 200:
            raise BackendError(f"unexpected backend status {response.status_code}")
        return response.json()

    def send_accounting(self, payload: Dict[str, Any]) -> bool:
        """Forward one accounting event. Best-effort: returns success."""
        try:
            response = self._client.post(
                f"{self.base_url}/wifi/accounting", json=payload
            )
        except httpx.HTTPError as exc:
            logger.error("accounting POST failed: %s", exc)
            return False
        if response.status_code != 200:
            logger.error(
                "accounting POST -> HTTP %s: %s",
                response.status_code,
                response.text[:200],
            )
            return False
        return True

    def close(self) -> None:
        self._client.close()
