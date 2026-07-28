"""Cached DST-aware application timezone service.

Spec: sales-reporting/spec.md — "Timezone Cache Consistency".

The configured IANA timezone is resolved through a Redis-backed cache so that
all report windows, dashboard/event date bucketing, and timestamp rendering use
a single consistent zone without re-reading the settings table on every query.
The cache is invalidated whenever the ``timezone`` setting is written (see
api/settings.py), so an admin's change takes effect on the next request without
a service restart.

Why ZoneInfo (not fixed ``timezone(timedelta(...))``): only a named IANA zone
can apply the correct UTC offset for each calendar date, which is required to
survive DST transitions (e.g. America/Santiago). DB columns remain naive UTC;
this service only affects how instants are bucketed and rendered.
"""

from datetime import datetime
from typing import Union
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from core.database import get_redis
from models.setting import Setting

DEFAULT_TZ = "America/Bogota"
CACHE_KEY = "app:tz"
TTL = 300  # seconds — bounded staleness as a safety net; writes invalidate eagerly


def get_app_tz(db: Session) -> ZoneInfo:
    """Resolve the configured application timezone as a DST-aware ZoneInfo.

    Redis-first: on a cache hit the DB is never touched. On a miss the
    ``timezone`` setting row is read (falling back to DEFAULT_TZ) and the
    result is cached with TTL. An invalid stored value falls back to
    DEFAULT_TZ rather than raising — reports must keep rendering.
    """
    r = get_redis()
    cached = r.get(CACHE_KEY)
    if cached:
        try:
            return ZoneInfo(cached)
        except (KeyError, ValueError):
            # Corrupted cache entry — fall through to a fresh DB read.
            r.delete(CACHE_KEY)

    name = _read_timezone_setting(db)
    r.setex(CACHE_KEY, TTL, name)
    return ZoneInfo(name)


def invalidate_app_tz_cache() -> None:
    """Drop the cached timezone so the next get_app_tz() re-reads the DB.

    Called by the settings write paths (PUT /{key} and POST /bulk) whenever
    the ``timezone`` key changes, implementing spec "Timezone changes during an
    active session" without a service restart.
    """
    get_redis().delete(CACHE_KEY)


def utc_to_local(dt_naive_utc: datetime, tz: ZoneInfo) -> datetime:
    """Render a naive-UTC DB timestamp in the configured timezone.

    DB timestamp columns are 'timestamp without time zone' storing UTC; this
    attaches UTC then converts to ``tz``, returning a tz-aware datetime whose
    ``.hour``/``.date()`` reflect local wall-clock time (DST-correct).
    """
    return dt_naive_utc.replace(tzinfo=timezone_utc()).astimezone(tz)


def timezone_utc() -> ZoneInfo:
    """UTC as a ZoneInfo (helper so callers avoid datetime.timezone import)."""
    return ZoneInfo("UTC")


# Allow get_app_tz to accept either a Session or a plain value in tests by
# keeping the DB read isolated and side-effect free apart from the query.
def _read_timezone_setting(db: Session) -> str:
    setting = db.query(Setting).filter(Setting.key == "timezone").first()
    value = getattr(setting, "value", None) if setting else None
    if isinstance(value, str) and value:
        candidate = value
    else:
        candidate = str(value) if value else DEFAULT_TZ
    try:
        ZoneInfo(candidate)
        return candidate
    except (KeyError, ValueError):
        return DEFAULT_TZ
