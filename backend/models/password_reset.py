"""
Password reset token model.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID

from core.database import Base


class PasswordResetToken(Base):
    """Password reset token for email-based password recovery."""
    __tablename__ = "password_reset_tokens"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    token = Column(String(64), nullable=False, unique=True, index=True)
    email = Column(String(255), nullable=False)
    used = Column(String(10), default="false")  # Using string to match DB style
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=False)
    
    __table_args__ = (
        Index('ix_prt_token', 'token'),
        Index('ix_prt_user', 'user_id'),
    )
