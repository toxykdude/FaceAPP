"""
Member model for member profiles.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from core.database import Base


class MemberStatus(str, enum.Enum):
    """Member status enum."""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    INACTIVE = "inactive"


class Member(Base):
    """Member model for gym members."""
    
    __tablename__ = "members"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=True, index=True)
    phone = Column(String(20), nullable=True)
    id_number = Column(String(20), nullable=True, index=True)
    
    status = Column(String(20), nullable=False, default=MemberStatus.ACTIVE.value)
    facial_data_enrolled = Column(Boolean, nullable=False, default=False)
    # biometric_template_id = Column(UUID(as_uuid=True), ForeignKey("biometric_templates.id"), nullable=True)
    consent_given_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_seen = Column(DateTime, nullable=True)
    
    # Relationships
    biometric_template = relationship(
        "BiometricTemplate", 
        back_populates="member", 
        uselist=False, 
        cascade="all, delete-orphan",
        primaryjoin="Member.id == BiometricTemplate.member_id"
    )
    memberships = relationship("Membership", back_populates="member", cascade="all, delete-orphan")
    sales_transactions = relationship("SalesTransaction", back_populates="member", cascade="all, delete-orphan")
    access_events = relationship("AccessEvent", back_populates="member", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Member {self.first_name} {self.last_name} ({self.status})>"
    
    @property
    def full_name(self):
        """Get full name."""
        return f"{self.first_name} {self.last_name}"
