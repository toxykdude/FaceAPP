"""
Access validation logic following SOPs.
"""

import time
from typing import Optional, Tuple, Dict
from datetime import datetime, date
from zoneinfo import ZoneInfo
import httpx
from loguru import logger

from api.backend_client import BackendAPIClient, _enforce_auth_config_ok

# Business-timezone cache: the configured app timezone is fetched from the
# backend once per TTL (modest staleness is fine — a wrong zone only shifts
# restriction windows by the TTL, and the window check still applies).
_TZ_CACHE: Dict[str, object] = {"zone": None, "fetched_at": 0.0}
_TZ_TTL_SECONDS = 300


class AccessValidator:
    """Validate access based on recognition results and membership rules."""

    def __init__(self):
        """Initialize access validator."""
        self.api_client = BackendAPIClient()

    async def _get_camera(self, camera_id: str) -> Optional[Dict]:
        """Get camera data from backend."""
        try:
            response = await self.api_client.client.get(
                f"{self.api_client.base_url}/cv/cameras"
            )
            if response.status_code == 200:
                cameras = response.json().get("cameras", [])
                for cam in cameras:
                    if cam["id"] == camera_id:
                        return cam
            return None
        except Exception:
            return None

    async def _get_app_timezone(self) -> Optional[str]:
        """Fetch the configured business timezone from the backend (cached).

        Returns the IANA zone name, or None when the fetch failed — the
        caller must then fail CLOSED on any day/time restriction (never
        grant on the host clock, which may disagree with the business
        timezone).

        Auth/config failures (401/403/503) propagate as RuntimeError via
        _enforce_auth_config_ok; transient errors are logged loudly and
        return None.
        """
        now = time.time()
        cached = _TZ_CACHE["zone"]
        if cached is not None and now - float(_TZ_CACHE["fetched_at"]) < _TZ_TTL_SECONDS:
            return str(cached)
        try:
            response = await self.api_client.client.get(
                f"{self.api_client.base_url}/cv/settings"
            )
            _enforce_auth_config_ok(response, "get_app_timezone")
            response.raise_for_status()
            zone = response.json().get("app_timezone")
            if zone:
                _TZ_CACHE["zone"] = zone
                _TZ_CACHE["fetched_at"] = now
                return str(zone)
            logger.error(
                "get_app_timezone: backend returned no app_timezone value"
            )
        except httpx.HTTPStatusError:
            logger.error("get_app_timezone: unexpected HTTP error")
        except httpx.RequestError as e:
            logger.error(f"get_app_timezone: network error: {e}")
        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"get_app_timezone: unexpected error: {e}")
        return None

    async def validate_access(
        self, member_id: Optional[str], confidence: float, camera_id: str
    ) -> Tuple[bool, Optional[str], Optional[int], Optional[float]]:
        """
        Validate access for recognized face.

        Args:
            member_id: Recognized member ID (None if unknown)
            confidence: Recognition confidence score
            camera_id: Camera ID

        Returns:
            Tuple of (access_granted, denial_reason, days_remaining, amount_due).

            days_remaining is the whole days left on the membership and is
            only populated on a grant — a denied member has no remaining-days
            figure to display. It may still be None on a grant when the
            membership carries no usable end_date.

            amount_due is the outstanding balance on that membership. A PARTIAL
            balance is reporting-only — the door still opens and the kiosk shows
            an amber reminder. A membership with NOTHING paid is denied outright
            ("unpaid_membership"), and that denial carries the amount so the
            kiosk can tell the member what to settle at reception. Every other
            denial reports None: only the payment denial is about money.
        """
        # Step 1: Check if face was matched
        if member_id is None:
            return False, "unknown_face", None, None

        # Step 2: Check confidence threshold (already done in matcher, but double-check)
        # Note: Confidence threshold is already applied in template matching
        # This is a safety check
        if confidence < 0.70:
            return False, "low_confidence", None, None

        # Step 3: Get member data
        member = await self.api_client.get_member(member_id)
        if not member:
            logger.error(f"Member {member_id} not found in database")
            return False, "member_not_found", None, None

        # Step 4: Check member status
        if member["status"] != "active":
            return False, f"member_{member['status']}", None, None

        # Step 5: Get active membership
        membership = await self.api_client.get_active_membership(member_id)
        if not membership:
            return False, "no_active_membership", None, None

        # Step 6: Check membership status
        if membership["status"] == "expired":
            return False, "expired_membership", None, None
        elif membership["status"] == "suspended":
            return False, "suspended_membership", None, None
        elif membership["status"] != "active":
            return False, f"membership_{membership['status']}", None, None

        # Step 7: Defense-in-depth date-window guard.
        # The backend (get_member_membership) is the source of truth and
        # already filters start_date<=today, but re-validate explicitly
        # here so display data (which may include a future-dated
        # membership) can never be mistaken for an access grant. The
        # "today" used is the business timezone's date.
        app_tz, tz_fetch_ok = await self._resolve_timezone()
        today = datetime.now(app_tz).date()

        try:
            membership_start = date.fromisoformat(membership.get("start_date", ""))
        except (TypeError, ValueError):
            membership_start = None

        if membership_start is not None and membership_start > today:
            return False, "membership_not_started", None, None

        # Step 8: Payment gate. A membership with NOTHING paid against it is not
        # a membership the member may use — they are denied and sent to
        # reception. A PARTIAL payment still opens the door (the kiosk shows an
        # amber reminder with the balance instead); only a zero payment blocks.
        #
        # This denies only on a POSITIVE report of non-payment. If the backend
        # omits payment_status (version skew during a rolling deploy) the member
        # is let in and the gap is logged, because failing closed here would
        # lock out every paying member at once — a far worse outcome than one
        # unpaid member training for one session. The identity and membership
        # window checks above remain fail-closed; this one is business policy,
        # not a security boundary.
        payment_status = membership.get("payment_status")
        if payment_status is None:
            logger.error(
                "Membership carries no payment_status — backend may predate the "
                "payment gate; granting access without a payment check"
            )
        elif payment_status == "pending":
            return False, "unpaid_membership", None, self._amount_due(membership)

        # Step 9: Check access rules
        access_rules = membership.get("access_rules", {})

        if access_rules:
            has_day_rules = bool(access_rules.get("allowed_days"))
            has_time_rules = bool(access_rules.get("time_windows"))

            if has_day_rules or has_time_rules:
                # The configured business timezone drives every day/time
                # restriction. If it cannot be resolved, deny — never fall
                # back to the host clock to grant access.
                if not tz_fetch_ok:
                    logger.error(
                        "Timezone unavailable with active day/time access "
                        "restrictions — denying access (fail closed)"
                    )
                    if has_day_rules:
                        return False, "access_day_restriction", None, None
                    return False, "access_time_restriction", None, None

                now_local = datetime.now(app_tz)
                current_day = now_local.strftime("%A").lower()
                current_time = now_local.time()

                # Check day of week
                if has_day_rules:
                    if current_day not in access_rules["allowed_days"]:
                        return False, "access_day_restriction", None, None

                # Check time windows
                if has_time_rules:
                    allowed = False
                    for window in access_rules["time_windows"]:
                        try:
                            start_time = datetime.strptime(
                                window["start_time"], "%H:%M:%S"
                            ).time()
                            end_time = datetime.strptime(
                                window["end_time"], "%H:%M:%S"
                            ).time()
                        except (KeyError, TypeError, ValueError):
                            logger.error(f"Malformed time window: {window}")
                            continue
                        if start_time <= current_time <= end_time:
                            allowed = True
                            break

                    if not allowed:
                        return False, "access_time_restriction", None, None

            # Check location restrictions — FAIL CLOSED. A camera whose
            # location cannot be positively matched to the allowed
            # location IDs is denied, never granted.
            location_ids = access_rules.get("location_ids") or []
            if location_ids:
                camera_data = await self._get_camera(camera_id)
                cam_location_id = (camera_data or {}).get("location_id")
                if cam_location_id is None or cam_location_id not in location_ids:
                    return False, "access_location_restriction", None, None

        # All checks passed — report how much membership is left, and anything
        # still owed on it, so the kiosk can warn a member whose membership is
        # about to lapse or who left a balance unpaid at reception.
        return (
            True,
            None,
            self._days_remaining(membership, today),
            self._amount_due(membership),
        )

    async def _resolve_timezone(self) -> Tuple[Optional[ZoneInfo], bool]:
        """Resolve the business timezone to a ZoneInfo.

        Returns (tz, ok). On a fetch failure ``tz`` is UTC and ``ok`` is
        False so callers can fail closed instead of trusting it for a grant.
        """
        zone_name = await self._get_app_timezone()
        if zone_name is None:
            logger.error(
                "Business timezone fetch failed — using UTC as a fail-closed "
                "fallback (day/time restrictions will DENY while this persists)"
            )
            return ZoneInfo("UTC"), False
        try:
            return ZoneInfo(zone_name), True
        except (KeyError, ValueError):
            logger.error(
                f"Backend returned an invalid timezone {zone_name!r} — using UTC "
                "as a fail-closed fallback"
            )
            return ZoneInfo("UTC"), False

    @staticmethod
    def _days_remaining(membership: Dict, today: date) -> Optional[int]:
        """
        Whole days left on a membership, or None when it can't be determined.

        A membership ending today yields 0, not None: 0 is a real value the
        kiosk warns on, while None means "unknown" and shows nothing.
        """
        try:
            end_date = date.fromisoformat(str(membership.get("end_date", "")))
        except (TypeError, ValueError):
            return None
        return (end_date - today).days

    @staticmethod
    def _amount_due(membership: Dict) -> Optional[float]:
        """Outstanding balance on a membership, or None when there is none.

        Returns None (not 0.0) for a settled membership so the kiosk has a
        single "nothing to say about money" signal and never renders a $0
        reminder. A malformed or missing value is also None: an unreadable
        balance must not invent a debt at the door.
        """
        raw = membership.get("amount_due")
        if raw is None:
            return None
        try:
            amount = float(raw)
        except (TypeError, ValueError):
            logger.error(f"Unreadable amount_due on membership: {raw!r}")
            return None
        return amount if amount > 0 else None

    async def close(self):
        """Close API client."""
        await self.api_client.close()
