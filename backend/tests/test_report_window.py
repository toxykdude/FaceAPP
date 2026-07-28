"""Pure-function tests for the custom date-range report window builder.

Contract (design.md): half-open ``[start_date 00:00, (end_date+1) 00:00)`` in
the application timezone (Colombia, UTC-5). Single-day == that whole day.
``start_date > end_date`` is rejected. DB timestamp columns are naive
'timestamp without time zone', so bounds are returned as naive UTC datetimes.
These tests are DB-free: pure logic only.
"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from services.report_window import build_report_window, DateRangeError

APP_TZ = timezone(timedelta(hours=-5))


def _utc(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi)


class TestBuildReportWindowHalfOpen:
    def test_single_day_window_is_exactly_that_day(self):
        # start == end == 2026-01-15: window is the whole Colombia day.
        start, end = build_report_window(date(2026, 1, 15), date(2026, 1, 15))
        # midnight -05:00 == 05:00 UTC; next-day midnight -05:00 == next day 05:00 UTC
        assert start == _utc(2026, 1, 15, 5)
        assert end == _utc(2026, 1, 16, 5)
        assert end - start == timedelta(days=1)

    def test_multi_day_window_is_inclusive_of_end_date(self):
        # 2026-01-10 .. 2026-01-20 (11 calendar days inclusive)
        start, end = build_report_window(date(2026, 1, 10), date(2026, 1, 20))
        assert start == _utc(2026, 1, 10, 5)
        assert end == _utc(2026, 1, 21, 5)  # (end_date + 1) 00:00 app tz
        assert end - start == timedelta(days=11)

    def test_end_date_midnight_is_excluded_half_open(self):
        # An instant equal to `end` is outside the half-open [start, end) window.
        start, end = build_report_window(date(2026, 3, 1), date(2026, 3, 1))
        assert start < end
        assert not (start <= end < end)


class TestBuildReportWindowValidation:
    def test_reversed_range_raises(self):
        with pytest.raises(DateRangeError):
            build_report_window(date(2026, 1, 20), date(2026, 1, 10))

    def test_reversed_range_error_message_mentions_order(self):
        with pytest.raises(DateRangeError, match="start"):
            build_report_window(date(2026, 2, 5), date(2026, 2, 1))

    def test_same_day_is_not_rejected(self):
        start, end = build_report_window(date(2026, 6, 1), date(2026, 6, 1))
        assert start == _utc(2026, 6, 1, 5)
        assert end == _utc(2026, 6, 2, 5)


class TestBuildReportWindowTimezone:
    def test_uses_app_timezone_default_and_returns_naive_utc(self):
        start, end = build_report_window(date(2026, 7, 16), date(2026, 7, 16))
        assert start.tzinfo is None
        assert end.tzinfo is None
        assert start == _utc(2026, 7, 16, 5)  # midnight Colombia == 05:00 UTC


class TestBuildReportWindowDSTAware:
    """Spec: Configured-Timezone Reporting — 'Report crosses an America/Santiago
    DST boundary'. Each local midnight must map using the offset applicable to
    THAT date (DST-aware), and the half-open contract is preserved.
    """

    def test_dst_boundary_each_midnight_uses_its_own_offset(self):
        # Santiago 2026: standard time UTC-4 until local midnight on 2026-09-06
        # (first Sunday of September), then DST UTC-3. A window spanning the
        # transition exercises per-date offset selection.
        start, end = build_report_window(
            date(2026, 9, 5), date(2026, 9, 8), tz=ZoneInfo("America/Santiago")
        )
        # 2026-09-05 00:00 Santiago (UTC-4) == 2026-09-05 04:00 UTC
        assert start == _utc(2026, 9, 5, 4)
        # (2026-09-08 + 1) 00:00 Santiago is DST (UTC-3) == 2026-09-09 03:00 UTC
        assert end == _utc(2026, 9, 9, 3)

    def test_dst_boundary_offsets_differ_across_the_window(self):
        # The whole window spans the transition, so the start and end bounds
        # are NOT a whole number of 24h apart (a fixed-offset impl would land
        # both on the same hour).
        start, end = build_report_window(
            date(2026, 9, 5), date(2026, 9, 8), tz=ZoneInfo("America/Santiago")
        )
        # 4 calendar days inclusive (Sep 5,6,7,8) but only 3d23h of UTC span
        # because the DST spring-forward removes an hour mid-window.
        assert end - start == timedelta(days=3, hours=23)

    def test_dst_boundary_half_open_preserved(self):
        start, end = build_report_window(
            date(2026, 9, 6), date(2026, 9, 9), tz=ZoneInfo("America/Santiago")
        )
        assert start < end
        # An instant equal to `end` is excluded (half-open).
        assert not (start <= end < end)
