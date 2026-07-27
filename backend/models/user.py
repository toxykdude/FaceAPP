"""
User model for authentication and authorization.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Enum, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
import enum

from core.database import Base


class UserRole(str, enum.Enum):
    """User roles for RBAC."""

    ADMIN = "admin"
    STAFF = "staff"


class User(Base):
    """User model for admin/staff authentication."""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default=UserRole.STAFF.value)
    is_active = Column(Boolean, nullable=False, default=True)
    permissions = Column(JSONB, nullable=False, default=lambda: {"pages": ["all"]})

    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_login = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"
