"""
Rate limiter instance shared across the application.
Separated from main.py to avoid circular imports.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Global rate limiter — 120 requests/minute as default fallback
# Per-endpoint limits are applied via @limiter.limit() decorators
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])
