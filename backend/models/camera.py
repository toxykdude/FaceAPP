"""
Camera model for RTSP camera configuration.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Boolean, Integer, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from core.database import Base


class Camera(Base):
    """Camera model for RTSP camera configuration."""
    
    __tablename__ = "cameras"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, nullable=False, index=True)
    rtsp_url = Column(String(500), nullable=False)  # Encrypted
    location = Column(String(200), nullable=True)
    location_id = Column(UUID(as_uuid=True), nullable=True)  # For access rules
    
    fps = Column(Integer, nullable=False, default=5)
    resolution_width = Column(Integer, nullable=False, default=1280)
    resolution_height = Column(Integer, nullable=False, default=720)
    
    enabled = Column(Boolean, nullable=False, default=True)
    confidence_threshold = Column(Float, nullable=False, default=0.85)
    
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_seen = Column(DateTime, nullable=True)  # Last successful frame
    
    # Relationships
    access_events = relationship("AccessEvent", back_populates="camera", passive_deletes=True)
    
    def __repr__(self):
        status = "ENABLED" if self.enabled else "DISABLED"
        return f"<Camera {self.name} ({status})>"
    
    @property
    def resolution(self):
        """Get resolution as tuple."""
        return (self.resolution_width, self.resolution_height)
