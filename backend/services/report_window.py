"""Custom date-range report window builder — centralises the half-open
reporting window so the dashboard and report summary apply an identical
interval. Contract (design.md): ``[start_date 00:00, (end_date+1) 00:00)`` in
the application timezone (default Colombia, UTC-5); single-day == that whole
day; ``start_date > end_date`` is rejected (callers surface as HTTP 422). DB
timestamp columns are naive, so bounds are returned as naive UTC datetimes.

The ``tz`` parameter accepts ANY ``tzinfo``. Callers that want DST-correct
behaviour pass the configured IANA zone via ``get_app_tz(db)`` (see
services/timezone.py and api/sales.py::_resolve_report_window); the legacy
``APP_TZ`` fixed-offset default is retained ONLY so the pure-function tests
stay green and single-process callers keep a sensible fallback.
"""

from datetime import date, datetime, time, timedelta, timezone
from typing import Tuple

# Application timezone (Colombia, UTC-5). Legacy fixed-offset default kept for
# pure-function tests and backward compatibility; production callers pass the
# configured DST-aware ZoneInfo (services.timezone.get_app_tz).
APP_TZ = timezone(timedelta(hours=-5))


class DateRangeError(ValueError):
    """Raised when a report date range is invalid (e.g. reversed)."""


def build_report_window(
    start_date: date,
    end_date: date,
    tz: timezone = APP_TZ,
) -> Tuple[datetime, datetime]:
    """Half-open ``[start, end)`` naive-UTC window for the inclusive dates.

    ``tz`` may be a fixed offset OR a DST-aware ``zoneinfo.ZoneInfo``; when a
    ZoneInfo is supplied, each local midnight is mapped with the offset
    applicable to THAT date, so windows crossing a DST transition stay correct.
    Raises DateRangeError if ``start_date`` is after ``end_date``."""
    if start_date > end_date:
        raise DateRangeError("start_date must not be after end_date")

    def _midnight_utc(d: date) -> datetime:
        midnight_local = datetime.combine(d, time(0, 0, 0)).replace(tzinfo=tz)
        return midnight_local.astimezone(timezone.utc).replace(tzinfo=None)

    window_start = _midnight_utc(start_date)
    window_end = _midnight_utc(end_date + timedelta(days=1))
    return window_start, window_end
