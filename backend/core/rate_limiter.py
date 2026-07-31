"""
Rate limiter instance shared across the application.
Separated from main.py to avoid circular imports.
"""

from slowapi import Limiter
from starlette.requests import Request


def real_client_ip(request: Request) -> str:
    """
    Extract the real client IP for rate limiting.

    Proxy ordering: Cloudflare terminates the client TLS connection and sets
    the ``CF-Connecting-IP`` header to the real client address. Behind it,
    Nginx (configured as a reverse proxy) APPENDS the real client address as
    the LAST ``X-Forwarded-For`` hop, so the last value in the chain is the
    client, not an intermediate proxy. Precedence:

    1. ``CF-Connecting-IP`` (set by Cloudflare, trusted — only our origin can
       spoof it, and Nginx strips/spoof-guards upstream headers in prod);
    2. last ``X-Forwarded-For`` hop (Nginx reverse-proxy deployments);
    3. ``request.client.host`` (direct connections, dev/test).
    """
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip

    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[-1].strip()

    client = request.client
    if client is not None:
        return client.host
    return "unknown"


# Global rate limiter — 120 requests/minute as default fallback
# Per-endpoint limits are applied via @limiter.limit() decorators
limiter = Limiter(key_func=real_client_ip, default_limits=["120/minute"])
