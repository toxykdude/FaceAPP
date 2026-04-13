"""
Access event model for recognition and access logs.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Boolean, Float, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from core.database import Base


class AccessEvent(Base):
    """Access event model for facial recognition events."""
    
    __tablename__ = "access_events"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    camera_id = Column(UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=False, index=True)
    member_id = Column(UUID(as_uuid=True), ForeignKey("members.id"), nullable=True, index=True)
    
    confidence_score = Column(Float, nullable=True)
    access_granted = Column(Boolean, nullable=False)
    denial_reason = Column(String(100), nullable=True)
    frame_snapshot_path = Column(Text, nullable=True)
    
    # Relationships
    camera = relationship("Camera", back_populates="access_events")
    member = relationship("Member", back_populates="access_events")
    
    def __repr__(self):
        status = "GRANTED" if self.access_granted else "DENIED"
        return f"<AccessEvent {status} at {self.timestamp}>"
