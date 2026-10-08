"""
WiFi captive-portal authorization service.

Decides whether a document number (cédula) may open a captive-portal session
on the member WiFi. The membership semantics intentionally mirror the kiosk's
`cv_service/validation/access_validator.py` so the door and the WiFi answer
the same question the same way:

  member active → membership status active → start_date <= today <= end_date
  (configured timezone) → something paid against the membership.

Deliberately NOT applied to WiFi (see design.md Decision 3): access_rules
day/time/location windows — those encode facility-entry policy, not network
use.

Timezone note (trap: never hardcode America/Bogota): "today" is resolved in
the configured application timezone via services.timezone, and the
Session-Timeout is computed against local midnight following the membership's
end_date so a membership ending "today" stays usable until tonight, matching
how the kiosk treats end_date as inclusive.
"""

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from core.config import settings
from models.member import Member, MemberStatus
from models.membership import Membership, MembershipStatus
from models.wifi_session import WifiSession
from services.timezone import get_app_tz

# --- Denial reasons (kiosk vocabulary) --------------------------------------

REASON_OK = None
REASON_MEMBER_NOT_FOUND = "member_not_found"
REASON_MEMBER_INACTIVE = "member_inactive"
REASON_NO_ACTIVE_MEMBERSHIP = "no_active_membership"
REASON_EXPIRED_MEMBERSHIP = "expired_membership"
REASON_SUSPENDED_MEMBERSHIP = "suspended_membership"
REASON_MEMBERSHIP_NOT_STARTED = "membership_not_started"
REASON_UNPAID_MEMBERSHIP = "unpaid_membership"
REASON_DEVICE_LIMIT = "device_limit"

# ES/EN portal text per reason. The Reply-Message shown by pfSense joins both
# ("ES / EN") because the captive portal cannot know the member's language.
MESSAGES = {
    REASON_MEMBER_NOT_FOUND: (
        "Cédula no encontrada. Regístrate en recepción.",
        "ID not found. Please register at reception.",
    ),
    REASON_MEMBER_INACTIVE: (
        "Tu registro está inactivo. Acércate a recepción.",
        "Your membership record is inactive. See reception.",
    ),
    REASON_NO_ACTIVE_MEMBERSHIP: (
        "No tienes una membresía activa. Actívala en recepción o en powerhousegym.co/portal.",
        "No active membership. Activate it at reception or powerhousegym.co/portal.",
    ),
    REASON_EXPIRED_MEMBERSHIP: (
        "Tu membresía venció. Renuévala en recepción o en powerhousegym.co/portal.",
        "Your membership expired. Renew at reception or powerhousegym.co/portal.",
    ),
    REASON_SUSPENDED_MEMBERSHIP: (
        "Tu membresía está suspendida. Acércate a recepción.",
        "Your membership is suspended. See reception.",
    ),
    REASON_MEMBERSHIP_NOT_STARTED: (
        "Tu membresía aún no inicia. Acércate a recepción.",
        "Your membership has not started yet. See reception.",
    ),
    REASON_UNPAID_MEMBERSHIP: (
        "Pendiente de pago. Regulariza en recepción para usar el WiFi.",
        "Payment pending. Settle at reception to use the WiFi.",
    ),
    REASON_DEVICE_LIMIT: (
        "Límite de dispositivos alcanzado. Cierra sesión en otro dispositivo.",
        "Device limit reached. Sign out on another device.",
    ),
}
GRANT_MESSAGES = (
    "¡Bienvenido a PowerHouse! Disfruta tu entrenamiento.",
    "Welcome to PowerHouse! Enjoy your training.",
)


def normalize_document(raw: str) -> str:
    """Canonical form for cédula comparison: alphanumerics only, uppercase.

    Handles members stored as "1.234.567" being looked up as "1234567"
    (and vice versa), foreigner IDs with letters, and stray whitespace.
    """
    return re.sub(r"[^0-9A-Za-z]", "", raw or "").upper()[:20]


def messages_for(reason: Optional[str]) -> Tuple[str, str]:
    """(message_es, message_en) for a denial reason, or the grant greeting."""
    if reason is None:
        return GRANT_MESSAGES
    return MESSAGES.get(reason, MESSAGES[REASON_NO_ACTIVE_MEMBERSHIP])


def _utcnow_naive() -> datetime:
    """Naive UTC 'now' matching the repo's naive-UTC timestamp columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _find_member(db: Session, normalized: str) -> Tuple[Optional[Member], str]:
    """Best matching member for a normalized document.

    Returns (member, reason). A member with an ACTIVE record always wins over
    inactive/suspended ones; when only inactive records match, the reason
    distinguishes "not found" from "found but inactive" so the portal message
    sends the person to the right desk.

    id_number has no unique constraint — duplicates are a data-quality
    reality, hence regexp normalization on both sides rather than an exact
    equality that would miss punctuation variants.
    """
    matches = (
        db.query(Member)
        .filter(
            func.upper(
                func.regexp_replace(
                    func.coalesce(Member.id_number, ""),
                    "[^0-9A-Za-z]",
                    "",
                    "g",
                )
            )
            == normalized
        )
        .all()
    )
    if not matches:
        return None, REASON_MEMBER_NOT_FOUND

    active = [m for m in matches if m.status == MemberStatus.ACTIVE.value]
    if active:
        return active[0], ""
    return None, REASON_MEMBER_INACTIVE


def _best_window_membership(
    db: Session, member_id, today: date
) -> Optional[Membership]:
    """Date-window-valid membership with the furthest end_date, any status."""
    return (
        db.query(Membership)
        .filter(
            Membership.member_id == str(member_id),
            Membership.start_date <= today,
            Membership.end_date >= today,
        )
        .order_by(Membership.end_date.desc(), Membership.created_at.desc())
        .first()
    )


def _latest_membership(db: Session, member_id) -> Optional[Membership]:
    """Most recent membership by end_date regardless of window/status."""
    return (
        db.query(Membership)
        .filter(Membership.member_id == str(member_id))
        .order_by(Membership.end_date.desc(), Membership.created_at.desc())
        .first()
    )


def _denial_for_member(db: Session, member: Member, today: date) -> Optional[str]:
    """Kiosk-order denial reason for a member, or None if grantable."""
    membership = _best_window_membership(db, member.id, today)
    if membership is None:
        latest = _latest_membership(db, member.id)
        if latest is None:
            return REASON_NO_ACTIVE_MEMBERSHIP
        if latest.start_date > today:
            return REASON_MEMBERSHIP_NOT_STARTED
        return REASON_EXPIRED_MEMBERSHIP

    if membership.status == MembershipStatus.SUSPENDED.value:
        return REASON_SUSPENDED_MEMBERSHIP
    if membership.status != MembershipStatus.ACTIVE.value:
        # expired/cancelled/pending inside the window
        return REASON_EXPIRED_MEMBERSHIP

    # Payment gate — mirrors kiosk Step 8: nothing collected blocks, partial
    # does not. payment_status derives from the transaction ledger.
    if membership.payment_status == "pending":
        return REASON_UNPAID_MEMBERSHIP

    return None


def _active_device_count(db: Session, member_id) -> int:
    """Open, freshly-updated sessions for a member (stale ones don't count).

    A lost Acct-Stop (client walked out of range, pfSense rebooted) would
    otherwise consume a device slot forever; sessions silent for
    WIFI_STALE_SESSION_HOURS are treated as gone.
    """
    cutoff = _utcnow_naive() - timedelta(hours=settings.WIFI_STALE_SESSION_HOURS)
    return (
        db.query(func.count(WifiSession.id))
        .filter(
            WifiSession.member_id == str(member_id),
            WifiSession.ended_at.is_(None),
            WifiSession.last_update_at >= cutoff,
        )
        .scalar()
        or 0
    )


def _session_timeout_seconds(membership: Membership, app_tz) -> int:
    """Seconds until the WiFi session must re-authenticate.

    Bounded by the configured cap so a membership-revocation or lapse is
    enforced within WIFI_SESSION_TIMEOUT_CAP_SECONDS at the latest (there is
    no push channel from the backend into pfSense's session table). The
    membership's own expiry wins when it is sooner: local midnight after
    end_date, i.e. end_date stays inclusive exactly like the kiosk treats it.
    """
    now_local = datetime.now(app_tz)
    expiry_local = datetime.combine(
        membership.end_date + timedelta(days=1), time.min, tzinfo=app_tz
    )
    remaining = int((expiry_local - now_local).total_seconds())
    return max(60, min(remaining, settings.WIFI_SESSION_TIMEOUT_CAP_SECONDS))


def evaluate_wifi_authorization(db: Session, document: str) -> dict:
    """Full authorization decision for a document number.

    Returns the dict shape of schemas.wifi.WiFiAuthorizeResponse.
    """
    normalized = normalize_document(document)
    if not normalized:
        es, en = messages_for(REASON_MEMBER_NOT_FOUND)
        return _decision(False, REASON_MEMBER_NOT_FOUND, message=(es, en))

    member, reason = _find_member(db, normalized)
    if member is None:
        es, en = messages_for(reason)
        return _decision(False, reason, message=(es, en))

    app_tz = get_app_tz(db)
    today = datetime.now(app_tz).date()

    reason = _denial_for_member(db, member, today)
    if reason is not None:
        es, en = messages_for(reason)
        return _decision(False, reason, message=(es, en))

    if _active_device_count(db, member.id) >= settings.WIFI_MAX_DEVICES_PER_MEMBER:
        es, en = messages_for(REASON_DEVICE_LIMIT)
        return _decision(False, REASON_DEVICE_LIMIT, message=(es, en))

    membership = _best_window_membership(db, member.id, today)
    plan_name = None
    if membership is not None and membership.plan is not None:
        plan_name = membership.plan.name

    es, en = messages_for(None)
    return _decision(
        True,
        None,
        message=(es, en),
        member=member,
        membership=membership,
        today=today,
        app_tz=app_tz,
        plan_name=plan_name,
    )


def _decision(
    allowed: bool,
    reason: Optional[str],
    message: Tuple[str, str],
    member: Optional[Member] = None,
    membership: Optional[Membership] = None,
    today: Optional[date] = None,
    app_tz=None,
    plan_name: Optional[str] = None,
) -> dict:
    es, en = message
    result = {
        "allowed": allowed,
        "reason": reason,
        "member_id": str(member.id) if member else None,
        "member_name": member.full_name if member else None,
        "plan_name": plan_name,
        "membership_end_date": None,
        "days_remaining": None,
        "session_timeout_seconds": None,
        "idle_timeout_seconds": None,
        "acct_interim_interval_seconds": None,
        "message_es": es,
        "message_en": en,
    }
    if allowed and membership is not None:
        result["membership_end_date"] = membership.end_date
        result["days_remaining"] = (membership.end_date - today).days
        result["session_timeout_seconds"] = _session_timeout_seconds(membership, app_tz)
        result["idle_timeout_seconds"] = settings.WIFI_IDLE_TIMEOUT_SECONDS
        result["acct_interim_interval_seconds"] = (
            settings.WIFI_ACCT_INTERIM_INTERVAL_SECONDS
        )
    return result
