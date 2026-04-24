"""
Login attempt tracking and account lockout.
Uses Redis to track failed login attempts per username.
After 5 failures within 5 minutes, the account is locked for 15 minutes.
"""
import redis
from core.config import settings

_redis_client = None

def _get_redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 900  # 15 minutes
ATTEMPT_WINDOW = 300   # 5 minutes

def _attempt_key(username: str) -> str:
    return f"auth_attempts:{username}"

def _lockout_key(username: str) -> str:
    return f"auth_lockout:{username}"

def is_locked_out(username: str) -> bool:
    """Check if account is temporarily locked."""
    r = _get_redis()
    return r.exists(_lockout_key(username)) > 0

def get_remaining_lockout(username: str) -> int:
    """Get remaining lockout seconds."""
    r = _get_redis()
    ttl = r.ttl(_lockout_key(username))
    return max(0, ttl) if ttl and ttl > 0 else 0

def record_failed_attempt(username: str) -> int:
    """Record a failed login attempt. Returns total attempts count."""
    r = _get_redis()
    key = _attempt_key(username)
    count = r.incr(key)
    if count == 1:
        r.expire(key, ATTEMPT_WINDOW)
    if count >= MAX_ATTEMPTS:
        r.setex(_lockout_key(username), LOCKOUT_SECONDS, "1")
        r.delete(key)
    return count

def clear_failed_attempts(username: str):
    """Clear failed attempts on successful login."""
    r = _get_redis()
    r.delete(_attempt_key(username))
