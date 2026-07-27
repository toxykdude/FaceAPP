"""Custom date-range report window builder — centralises the half-open
reporting window so the dashboard and report summary apply an identical
interval. Contract (design.md): ``[start_date 00:00, (end_date+1) 00:00)`` in
the application timezone (Colombia, UTC-5); single-day == that whole day;
``start_date > end_date`` is rejected (callers surface as HTTP 422). DB
timestamp columns are naive, so bounds are returned as naive UTC datetimes.
"""
from datetime import date, datetime, time, timedelta, timezone
from typing import Tuple

# Application timezone (Colombia, UTC-5). Kept in sync with dashboard_service.
APP_TZ = timezone(timedelta(hours=-5))


class DateRangeError(ValueError):
    """Raised when a report date range is invalid (e.g. reversed)."""


def build_report_window(
    start_date: date,
    end_date: date,
    tz: timezone = APP_TZ,
) -> Tuple[datetime, datetime]:
    """Half-open ``[start, end)`` naive-UTC window for the inclusive dates.
    Raises DateRangeError if ``start_date`` is after ``end_date``."""
    if start_date > end_date:
        raise DateRangeError("start_date must not be after end_date")

    def _midnight_utc(d: date) -> datetime:
        midnight_local = datetime.combine(d, time(0, 0, 0)).replace(tzinfo=tz)
        return midnight_local.astimezone(timezone.utc).replace(tzinfo=None)

    window_start = _midnight_utc(start_date)
    window_end = _midnight_utc(end_date + timedelta(days=1))
    return window_start, window_end
