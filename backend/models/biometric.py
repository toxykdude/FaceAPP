"""
Biometric template model for encrypted facial data storage.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, Float, ForeignKey, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from core.database import Base


class BiometricTemplate(Base):
    """Biometric template model for encrypted facial embeddings."""
    
    __tablename__ = "biometric_templates"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id = Column(UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    
    # Encrypted template data (AES-256-GCM)
    template_data = Column(LargeBinary, nullable=False)
    encryption_key_id = Column(String(50), nullable=False, default="v1")  # Key version for rotation
    
    quality_score = Column(Float, nullable=False)
    enrolled_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    member = relationship(
        "Member", 
        back_populates="biometric_template", 
        primaryjoin="BiometricTemplate.member_id == Member.id"
    )
    
    def __repr__(self):
        return f"<BiometricTemplate for Member {self.member_id} (quality: {self.quality_score:.2f})>"
