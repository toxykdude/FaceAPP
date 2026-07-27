"""
Audit log model for tracking user actions.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text, Index
from sqlalchemy.dialects.postgresql import UUID

from core.database import Base


class AuditLog(Base):
    """Audit log for tracking user actions in the system."""

    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True), nullable=True, index=True
    )  # Null for system actions
    username = Column(String(100), nullable=True)
    action = Column(
        String(50), nullable=False, index=True
    )  # create, update, delete, login, logout
    resource_type = Column(
        String(50), nullable=False, index=True
    )  # member, membership, camera, user, etc.
    resource_id = Column(String(255), nullable=True, index=True)
    details = Column(Text, nullable=True)  # JSON string with change details
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent = Column(String(500), nullable=True)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )

    __table_args__ = (
        Index("ix_audit_logs_resource", "resource_type", "resource_id"),
        Index("ix_audit_logs_created", "created_at"),
    )
