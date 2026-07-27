"""
Shared CV-service cache-invalidation notifier.

Extracted from the logic that previously lived only inline in
`api/members.py` so every membership write path (admin renewal, portal
self-service renewal, portal webhook renewal, member update/delete) can
invalidate the CV service's cached template/membership data through the
exact same contract.

Best-effort by design: the CV service may be down and this must never
block or fail the caller's response.
"""
import httpx

from core.config import settings


async def notify_cv_invalidation(member_id: str) -> None:
    """POST {CV_SERVICE_URL}/invalidate/{member_id} with X-API-Key auth."""
    try:
        headers = {}
        if settings.CV_API_KEY:
            headers["X-API-Key"] = settings.CV_API_KEY
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{settings.CV_SERVICE_URL}/invalidate/{member_id}",
                headers=headers,
            )
    except Exception:
        pass  # CV service might be down, non-critical
