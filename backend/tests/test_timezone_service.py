"""Unit tests for the cached DST-aware application timezone service.

Spec: sales-reporting/spec.md — "Timezone Cache Consistency".
- default zone is America/Bogota when no setting is stored
- reads the configured `timezone` setting (IANA name)
- Redis cache hit skips the DB read
- invalidate_app_tz_cache() forces the next get_app_tz() to re-read
- utc_to_local converts a naive-UTC DB timestamp to a tz-aware local datetime
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from core.database import get_redis
from models.setting import Setting
from services.timezone import (
    CACHE_KEY,
    DEFAULT_TZ,
    get_app_tz,
    invalidate_app_tz_cache,
    utc_to_local,
)


@pytest.fixture(autouse=True)
def _clear_tz_cache():
    """Ensure a cold cache before every test so assertions are deterministic."""
    r = get_redis()
    r.delete(CACHE_KEY)
    yield
    r.delete(CACHE_KEY)


def _seed_timezone(db_session, value):
    """Upsert the `timezone` setting row (value column is JSON)."""
    existing = db_session.query(Setting).filter(Setting.key == "timezone").first()
    if existing:
        existing.value = value
    else:
        db_session.add(Setting(key="timezone", value=value, category="system"))
    db_session.flush()


class TestGetAppTzDefault:
    def test_returns_default_when_no_setting_stored(self, db_session):
        # No timezone row -> service falls back to DEFAULT_TZ.
        db_session.query(Setting).filter(Setting.key == "timezone").delete()
        db_session.flush()
        tz = get_app_tz(db_session)
        assert tz == ZoneInfo(DEFAULT_TZ)


class TestGetAppTzReadsSetting:
    def test_reads_configured_iana_timezone(self, db_session):
        _seed_timezone(db_session, "America/Santiago")
        tz = get_app_tz(db_session)
        assert tz == ZoneInfo("America/Santiago")

    def test_returns_dst_aware_zoneinfo_not_fixed_offset(self, db_session):
        _seed_timezone(db_session, "America/Santiago")
        tz = get_app_tz(db_session)
        # A ZoneInfo reflects DST: two different dates yield two offsets.
        winter = datetime(2026, 6, 1, tzinfo=tz).utcoffset()
        summer = datetime(2026, 12, 1, tzinfo=tz).utcoffset()
        assert winter != summer


class TestGetAppTzCache:
    def test_cache_hit_skips_db_read(self, db_session):
        # Seed a value, warm the cache, then DELETE the row. A cached read
        # must still return the originally-seeded zone (cache served, no DB).
        _seed_timezone(db_session, "America/Bogota")
        first = get_app_tz(db_session)  # warms cache
        assert first == ZoneInfo("America/Bogota")

        db_session.query(Setting).filter(Setting.key == "timezone").delete()
        db_session.flush()

        cached = get_app_tz(db_session)
        assert cached == ZoneInfo("America/Bogota")

    def test_invalidate_forces_reread_of_new_zone(self, db_session):
        _seed_timezone(db_session, "America/Bogota")
        first = get_app_tz(db_session)
        assert first == ZoneInfo("America/Bogota")

        # Admin saves a different valid IANA timezone.
        _seed_timezone(db_session, "America/Santiago")
        invalidate_app_tz_cache()

        next_tz = get_app_tz(db_session)
        assert next_tz == ZoneInfo("America/Santiago")


class TestUtcToLocal:
    def test_converts_naive_utc_to_aware_local(self):
        tz = ZoneInfo("America/Bogota")  # UTC-5
        # 2026-01-15 10:00 UTC -> 05:00 Colombia
        local = utc_to_local(datetime(2026, 1, 15, 10, 0, 0), tz)
        assert local.utcoffset() is not None  # aware
        # Hour in the configured zone is 05:00.
        assert local.hour == 5
        assert local.tzinfo is tz

    def test_dst_correct_conversion_for_santiago(self):
        tz = ZoneInfo("America/Santiago")
        # Santiago springs forward to UTC-3 at local midnight on 2026-09-06
        # (first Sunday of September), so Sep 5 is UTC-4 and Sep 7 is UTC-3.
        # Pre-DST local midnight: 2026-09-05 00:00 Santiago (UTC-4) == 04:00 UTC.
        before = utc_to_local(datetime(2026, 9, 5, 4, 0, 0), tz)
        # Post-DST local midnight: 2026-09-07 00:00 Santiago (UTC-3) == 03:00 UTC.
        after = utc_to_local(datetime(2026, 9, 7, 3, 0, 0), tz)
        assert before.hour == 0
        assert after.hour == 0
        assert before.date() != after.date()
        # Same local midnight hour, but a different UTC offset: DST-aware.
        assert before.utcoffset().total_seconds() == -4 * 3600  # UTC-4
        assert after.utcoffset().total_seconds() == -3 * 3600  # UTC-3
