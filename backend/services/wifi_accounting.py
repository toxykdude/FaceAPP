"""
WiFi captive-portal accounting persistence.

Translates RADIUS accounting events (already decoded by the radius_service
into schemas.wifi.WiFiAccountingRequest) into wifi_sessions rows.

Idempotency contract: pfSense retransmits accounting packets when it does not
see the Accounting-Response in time, so every branch here must tolerate
duplicates. The row key is (nas_ip, acct_session_id); octet counters are
monotonic (an out-of-order retransmission must never shrink them).
"""

from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.member import Member, MemberStatus
from models.wifi_session import WifiSession
from schemas.wifi import WiFiAccountingRequest
from services.wifi_auth import _utcnow_naive, normalize_document


def _resolve_member_id(db: Session, username: str) -> Optional[UUID]:
    """Best-effort member resolution for an accounting username.

    Accounting must record even when the document does not resolve (the
    session may outlive the member record), so failures return None rather
    than raising. Matches the authorize lookup: normalized id_number on an
    ACTIVE member.
    """
    normalized = normalize_document(username)
    if not normalized:
        return None
    member = (
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
            == normalized,
            Member.status == MemberStatus.ACTIVE.value,
        )
        .first()
    )
    return member.id if member else None


def _find_session(db: Session, payload: WiFiAccountingRequest) -> Optional[WifiSession]:
    return (
        db.query(WifiSession)
        .filter(
            WifiSession.nas_ip == payload.nas_ip,
            WifiSession.acct_session_id == payload.acct_session_id,
        )
        .first()
    )


def record_wifi_accounting(
    db: Session, payload: WiFiAccountingRequest
) -> Tuple[Optional[UUID], Optional[UUID]]:
    """Apply one accounting event; returns (wifi_session_id, member_id).

    start   → create if absent (idempotent), keep open
    interim → refresh counters/last_update_at on the existing row (create if
              missing — an interim can legitimately arrive after a restart
              lost the start)
    stop    → set ended_at/terminate_cause once; repeated stops are no-ops
    """
    row = _find_session(db, payload)

    if row is None:
        row = WifiSession(
            member_id=_resolve_member_id(db, payload.username),
            username=payload.username[:64],
            nas_ip=payload.nas_ip,
            acct_session_id=payload.acct_session_id,
            framed_ip=payload.framed_ip,
            calling_station_id=payload.calling_station_id,
        )
        db.add(row)

    # Snapshot the connection coordinates on every event — a start may have
    # omitted them and pfSense fills them in on later packets.
    if payload.framed_ip:
        row.framed_ip = payload.framed_ip
    if payload.calling_station_id:
        row.calling_station_id = payload.calling_station_id
    if payload.acct_session_time is not None:
        row.acct_session_time = payload.acct_session_time

    # Cumulative RADIUS counters: keep the maximum ever reported.
    row.acct_input_octets = max(row.acct_input_octets or 0, payload.acct_input_octets)
    row.acct_output_octets = max(
        row.acct_output_octets or 0, payload.acct_output_octets
    )

    if payload.status == "stop":
        if row.ended_at is None:
            # Local naive-UTC now (house convention for naive-UTC columns);
            # packet Event-Timestamp is display metadata, not a trusted clock.
            row.ended_at = _utcnow_naive()
            row.terminate_cause = payload.acct_terminate_cause
        # A repeated Stop (retransmission) changes nothing.
    else:
        # start / interim: (re)open. A start arriving after a stop (session
        # id reuse after a pfSense reboot) reopens the row for the new run.
        row.ended_at = None
        row.terminate_cause = None

    db.flush()
    return row.id, row.member_id
