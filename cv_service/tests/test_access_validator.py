"""
Tests for the defense-in-depth start_date guard in AccessValidator.

ACCESS must always enforce start_date<=today AND end_date>=today. The
backend (`get_member_membership`) is the source of truth for this window,
but AccessValidator re-validates it explicitly here as defense-in-depth.
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


def _membership(start_offset_days, end_offset_days, status="active"):
    today = date.today()
    return {
        "id": "membership-1",
        "type": "monthly",
        "status": status,
        "start_date": (today + timedelta(days=start_offset_days)).isoformat(),
        "end_date": (today + timedelta(days=end_offset_days)).isoformat(),
        "access_rules": {},
    }


class TestAccessValidatorStartDateGuard:
    @pytest.mark.asyncio
    async def test_denies_access_before_start_date(self):
        validator = AccessValidator()
        validator.api_client = _FakeApiClient(
            member={"status": "active"},
            membership=_membership(start_offset_days=5, end_offset_days=40),
        )

        granted, reason = await validator.validate_access("member-1", 0.95, "cam-1")

        assert granted is False
        assert reason == "membership_not_started"

    @pytest.mark.asyncio
    async def test_grants_access_at_start_boundary(self):
        validator = AccessValidator()
        validator.api_client = _FakeApiClient(
            member={"status": "active"},
            membership=_membership(start_offset_days=0, end_offset_days=30),
        )

        granted, reason = await validator.validate_access("member-1", 0.95, "cam-1")

        assert granted is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_grants_access_mid_window_far_from_start(self):
        """Triangulation: a membership well past its start (not boundary)
        still grants access — the guard only blocks FUTURE starts."""
        validator = AccessValidator()
        validator.api_client = _FakeApiClient(
            member={"status": "active"},
            membership=_membership(start_offset_days=-10, end_offset_days=5),
        )

        granted, reason = await validator.validate_access("member-1", 0.95, "cam-1")

        assert granted is True
        assert reason is None
