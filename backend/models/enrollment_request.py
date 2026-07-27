"""
Enrollment request model — queue for remote enrollment from Android tablet.

Flow:
1. Admin creates request from frontend → status="pending"
2. Android polls for pending requests → picks up → status="processing"
3. Android captures face + uploads image → status="complete" (or "failed")
4. Frontend polls for result → shows success/failure
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, String, Float, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from core.database import Base


class EnrollmentRequest(Base):
    """Enrollment request queue for remote Android enrollment."""

    __tablename__ = "enrollment_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Who to enroll
    member_id = Column(
        UUID(as_uuid=True),
        ForeignKey("members.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Which device should handle this (scalable for multiple tablets)
    device_id = Column(String(100), nullable=False, default="kiosk-android", index=True)

    # Status: pending → processing → complete / failed / cancelled
    status = Column(String(20), nullable=False, default="pending", index=True)

    # Result fields (filled when complete/failed)
    quality_score = Column(Float, nullable=True)
    result_message = Column(Text, nullable=True)

    # Who created the request (admin user)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Timestamps
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    member = relationship("Member", backref="enrollment_requests")
    creator = relationship("User", foreign_keys=[created_by])

    def __repr__(self):
        return f"<EnrollmentRequest {self.id} member={self.member_id} status={self.status}>"
