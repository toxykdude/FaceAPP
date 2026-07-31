"""
Tests for AccessValidator's access decision contract.

Two concerns are covered here:

1. The defense-in-depth start_date guard. ACCESS must always enforce
   start_date<=today AND end_date>=today. The backend
   (`get_member_membership`) is the source of truth for this window, but
   AccessValidator re-validates it explicitly here as defense-in-depth.

2. The days_remaining value returned alongside the decision. The kiosk
   renders an "expiring soon" warning from it, so it must be present on
   every grant and absent on every denial.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from validation.access_validator import AccessValidator

# The validator resolves the business timezone from the backend; every fake
# reports this zone so day/time windows and dates are deterministic.
TEST_TZ = "America/Bogota"
TEST_ZONE = ZoneInfo(TEST_TZ)


class _FakeResponse:
    def __init__(self, data):
        self._data = data
        self.status_code = 200

    def json(self):
        return self._data

    def raise_for_status(self):
        return None


class _FakeApiClient:
    """Stands in for BackendAPIClient — no network calls."""

    def __init__(self, member, membership, timezone=TEST_TZ):
        self._member = member
        self._membership = membership
        self.base_url = "http://backend/api"
        self.client = SimpleNamespace(
            get=AsyncMock(return_value=_FakeResponse({"app_timezone": timezone}))
        )

    async def get_member(self, member_id):
        return self._member

    async def get_active_membership(self, member_id):
        return self._membership

    async def _get_camera(self, camera_id):
        return None

    async def close(self):
        pass


def _membership(start_offset_days, end_offset_days, status="active", **overrides):
    # Offsets are relative to the business timezone's today so boundary
    # assertions stay deterministic regardless of the host clock.
    today = datetime.now(TEST_ZONE).date()
    membership = {
        "id": "membership-1",
        "type": "monthly",
        "status": status,
        "start_date": (today + timedelta(days=start_offset_days)).isoformat(),
        "end_date": (today + timedelta(days=end_offset_days)).isoformat(),
        "access_rules": {},
    }
    membership.update(overrides)
    return membership


def _validator(member, membership):
    validator = AccessValidator()
    validator.api_client = _FakeApiClient(member=member, membership=membership)
    return validator


class TestAccessValidatorStartDateGuard:
    @pytest.mark.asyncio
    async def test_denies_access_before_start_date(self):
        validator = _validator(
            member={"status": "active"},
            membership=_membership(start_offset_days=5, end_offset_days=40),
        )

        granted, reason, days_remaining = await validator.validate_access(
            "member-1", 0.95, "cam-1"
        )

        assert granted is False
        assert reason == "membership_not_started"
        assert days_remaining is None

    @pytest.mark.asyncio
    async def test_grants_access_at_start_boundary(self):
        validator = _validator(
            member={"status": "active"},
            membership=_membership(start_offset_days=0, end_offset_days=30),
        )

        granted, reason, _ = await validator.validate_access("member-1", 0.95, "cam-1")

        assert granted is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_grants_access_mid_window_far_from_start(self):
        """Triangulation: a membership well past its start (not boundary)
        still grants access — the guard only blocks FUTURE starts."""
        validator = _validator(
            member={"status": "active"},
            membership=_membership(start_offset_days=-10, end_offset_days=5),
        )

        granted, reason, _ = await validator.validate_access("member-1", 0.95, "cam-1")

        assert granted is True
        assert reason is None


class TestAccessValidatorDaysRemaining:
    """days_remaining drives the kiosk's amber "expiring soon" splash."""

    @pytest.mark.asyncio
    async def test_grant_reports_days_until_end_date(self):
        validator = _validator(
            member={"status": "active"},
            membership=_membership(start_offset_days=-10, end_offset_days=12),
        )

        granted, _, days_remaining = await validator.validate_access(
            "member-1", 0.95, "cam-1"
        )

        assert granted is True
        assert days_remaining == 12

    @pytest.mark.asyncio
    async def test_grant_on_final_day_reports_zero_not_none(self):
        """A membership ending today is still valid, and must report 0 —
        not None. None means "unknown" to the kiosk and would suppress the
        expiring-soon warning on the very day it matters most."""
        validator = _validator(
            member={"status": "active"},
            membership=_membership(start_offset_days=-30, end_offset_days=0),
        )

        granted, _, days_remaining = await validator.validate_access(
            "member-1", 0.95, "cam-1"
        )

        assert granted is True
        assert days_remaining == 0

    @pytest.mark.asyncio
    async def test_denial_never_reports_days_remaining(self):
        """Triangulation across denial categories: a denied member has no
        remaining-days figure to show."""
        validator = _validator(
            member={"status": "active"},
            membership=_membership(
                start_offset_days=-30, end_offset_days=-1, status="expired"
            ),
        )

        granted, reason, days_remaining = await validator.validate_access(
            "member-1", 0.95, "cam-1"
        )

        assert granted is False
        assert reason == "expired_membership"
        assert days_remaining is None

    @pytest.mark.asyncio
    async def test_unknown_face_reports_no_days_remaining(self):
        validator = _validator(member=None, membership=None)

        granted, reason, days_remaining = await validator.validate_access(
            None, 0.95, "cam-1"
        )

        assert granted is False
        assert reason == "unknown_face"
        assert days_remaining is None

    @pytest.mark.asyncio
    async def test_grant_tolerates_unusable_end_date(self):
        """A malformed or missing end_date must degrade to None rather than
        blowing up the recognition pipeline mid-frame."""
        validator = _validator(
            member={"status": "active"},
            membership=_membership(
                start_offset_days=-10, end_offset_days=10, end_date="not-a-date"
            ),
        )

        granted, reason, days_remaining = await validator.validate_access(
            "member-1", 0.95, "cam-1"
        )

        assert granted is True
        assert reason is None
        assert days_remaining is None


class TestAccessValidatorTimezoneAwareRules:
    """Day/time restrictions must run on the business timezone, never the
    host clock (WS-7b)."""

    @pytest.mark.asyncio
    async def test_day_restriction_denies_other_day(self):
        current_day = datetime.now(TEST_ZONE).strftime("%A").lower()
        other_day = "monday" if current_day != "monday" else "tuesday"
        validator = _validator(
            member={"status": "active"},
            membership=_membership(
                start_offset_days=-10,
                end_offset_days=10,
                access_rules={"allowed_days": [other_day]},
            ),
        )

        granted, reason, _ = await validator.validate_access(
            "member-1", 0.95, "cam-1"
        )

        assert granted is False
        assert reason == "access_day_restriction"

    @pytest.mark.asyncio
    async def test_day_restriction_allows_current_day(self):
        current_day = datetime.now(TEST_ZONE).strftime("%A").lower()
        validator = _validator(
            member={"status": "active"},
            membership=_membership(
                start_offset_days=-10,
                end_offset_days=10,
                access_rules={"allowed_days": [current_day]},
            ),
        )

        granted, reason, _ = await validator.validate_access(
            "member-1", 0.95, "cam-1"
        )

        assert granted is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_time_window_denies_outside_window(self):
        now = datetime.now(TEST_ZONE)
        future_start = (now + timedelta(hours=1)).strftime("%H:%M:%S")
        future_end = (now + timedelta(hours=2)).strftime("%H:%M:%S")
        validator = _validator(
            member={"status": "active"},
            membership=_membership(
                start_offset_days=-10,
                end_offset_days=10,
                access_rules={
                    "time_windows": [
                        {"start_time": future_start, "end_time": future_end}
                    ]
                },
            ),
        )

        granted, reason, _ = await validator.validate_access(
            "member-1", 0.95, "cam-1"
        )

        assert granted is False
        assert reason == "access_time_restriction"

    @pytest.mark.asyncio
    async def test_time_window_grants_inside_window(self):
        now = datetime.now(TEST_ZONE)
        start = (now - timedelta(minutes=5)).strftime("%H:%M:%S")
        end = (now + timedelta(minutes=5)).strftime("%H:%M:%S")
        validator = _validator(
            member={"status": "active"},
            membership=_membership(
                start_offset_days=-10,
                end_offset_days=10,
                access_rules={
                    "time_windows": [
                        {"start_time": start, "end_time": end}
                    ]
                },
            ),
        )

        granted, reason, _ = await validator.validate_access(
            "member-1", 0.95, "cam-1"
        )

        assert granted is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_timezone_fetch_failure_denies_day_restriction(self):
        """Never grant on a day/time restriction when the business timezone
        cannot be resolved — fail closed (WS-7b)."""
        current_day = datetime.now(TEST_ZONE).strftime("%A").lower()
        validator = _validator(
            member={"status": "active"},
            membership=_membership(
                start_offset_days=-10,
                end_offset_days=10,
                access_rules={"allowed_days": [current_day]},
            ),
        )
        validator._get_app_timezone = AsyncMock(return_value=None)

        granted, reason, _ = await validator.validate_access(
            "member-1", 0.95, "cam-1"
        )

        assert granted is False
        assert reason == "access_day_restriction"


class TestAccessValidatorLocationFailClosed:
    """Location restrictions compare like-for-like on the camera's
    location_id, and any unresolvable camera location DENIES (WS-7b)."""

    @pytest.mark.asyncio
    async def test_location_mismatch_denies(self):
        validator = _validator(
            member={"status": "active"},
            membership=_membership(
                start_offset_days=-10,
                end_offset_days=10,
                access_rules={"location_ids": ["loc-1"]},
            ),
        )
        validator._get_camera = AsyncMock(
            return_value={"id": "cam-1", "location": "Lobby", "location_id": "loc-2"}
        )

        granted, reason, _ = await validator.validate_access(
            "member-1", 0.95, "cam-1"
        )

        assert granted is False
        assert reason == "access_location_restriction"

    @pytest.mark.asyncio
    async def test_location_label_cannot_match_ids(self):
        """The legacy label-vs-id comparison must NOT grant: a camera whose
        location_id is missing is denied even when its label string would
        'match' an ID-looking value."""
        validator = _validator(
            member={"status": "active"},
            membership=_membership(
                start_offset_days=-10,
                end_offset_days=10,
                access_rules={"location_ids": ["Lobby"]},
            ),
        )
        validator._get_camera = AsyncMock(
            return_value={"id": "cam-1", "location": "Lobby", "location_id": None}
        )

        granted, reason, _ = await validator.validate_access(
            "member-1", 0.95, "cam-1"
        )

        assert granted is False
        assert reason == "access_location_restriction"

    @pytest.mark.asyncio
    async def test_unknown_camera_denies(self):
        """camera_data None (camera missing/disabled) must DENY, never skip
        the restriction."""
        validator = _validator(
            member={"status": "active"},
            membership=_membership(
                start_offset_days=-10,
                end_offset_days=10,
                access_rules={"location_ids": ["loc-1"]},
            ),
        )
        validator._get_camera = AsyncMock(return_value=None)

        granted, reason, _ = await validator.validate_access(
            "member-1", 0.95, "cam-1"
        )

        assert granted is False
        assert reason == "access_location_restriction"

    @pytest.mark.asyncio
    async def test_location_match_grants(self):
        validator = _validator(
            member={"status": "active"},
            membership=_membership(
                start_offset_days=-10,
                end_offset_days=10,
                access_rules={"location_ids": ["loc-1"]},
            ),
        )
        validator._get_camera = AsyncMock(
            return_value={"id": "cam-1", "location": "Lobby", "location_id": "loc-1"}
        )

        granted, reason, _ = await validator.validate_access(
            "member-1", 0.95, "cam-1"
        )

        assert granted is True
        assert reason is None
