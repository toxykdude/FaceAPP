"""
WiFi captive-portal session model.

One row per RADIUS accounting session opened by the pfSense captive portal
through the radius_service (see docs/pfsense-captive-portal.md). Rows are
written exclusively by the internal /wifi/accounting endpoint; admins read
them through /wifi/sessions.

`username` snapshots the document number (cédula) as RADIUS reported it, so
the row survives member deletion (member_id drops to NULL via SET NULL) and
remains meaningful for audits even when the document no longer resolves.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from core.database import Base


class WifiSession(Base):
    """WiFi Captive Portal accounting session (RADIUS Acct start→stop)."""

    __tablename__ = "wifi_sessions"
    __table_args__ = (
        # RADIUS session identity: the NAS (pfSense) assigns Acct-Session-Id
        # values unique per device session; scoping by nas_ip keeps two
        # firewalls from colliding.
        UniqueConstraint(
            "nas_ip", "acct_session_id", name="uq_wifi_sessions_nas_acct_id"
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Resolved at Acct-Start from the username; NULL-able and severed on
    # member delete (SET NULL) — the username snapshot keeps the row legible.
    member_id = Column(
        UUID(as_uuid=True),
        ForeignKey("members.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Document number exactly as the portal submitted it (snapshot).
    username = Column(String(64), nullable=False, index=True)

    nas_ip = Column(String(64), nullable=False, default="")
    acct_session_id = Column(String(128), nullable=False, default="")
    framed_ip = Column(String(64), nullable=True)
    calling_station_id = Column(String(32), nullable=True)  # client MAC

    # Cumulative counters as reported by RADIUS (monotonic per session).
    acct_input_octets = Column(BigInteger, nullable=False, default=0)
    acct_output_octets = Column(BigInteger, nullable=False, default=0)
    acct_session_time = Column(Integer, nullable=True)

    started_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    last_update_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    ended_at = Column(DateTime, nullable=True, index=True)
    terminate_cause = Column(String(64), nullable=True)

    def __repr__(self):
        return (
            f"<WifiSession {self.username} mac={self.calling_station_id} "
            f"ended={self.ended_at is not None}>"
        )
