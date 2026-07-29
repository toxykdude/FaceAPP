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

from datetime import date, timedelta

import pytest

from validation.access_validator import AccessValidator


class _FakeApiClient:
    """Stands in for BackendAPIClient — no network calls."""

    def __init__(self, member, membership):
        self._member = member
        self._membership = membership

    async def get_member(self, member_id):
        return self._member

    async def get_active_membership(self, member_id):
        return self._membership

    async def _get_camera(self, camera_id):
        return None

    async def close(self):
        pass


def _membership(start_offset_days, end_offset_days, status="active", **overrides):
    today = date.today()
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
