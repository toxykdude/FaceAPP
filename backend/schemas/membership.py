"""
Pydantic schemas for Membership model.
"""

from pydantic import BaseModel, Field, field_serializer
from typing import Optional, List, Any
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from models.membership import MembershipType, MembershipStatus


class AccessRules(BaseModel):
    """Access rules schema."""

    allowed_days: Optional[List[str]] = None  # ["monday", "tuesday", ...]
    time_windows: Optional[List[dict]] = (
        None  # [{"start_time": "06:00:00", "end_time": "22:00:00"}]
    )
    location_ids: Optional[List[str]] = None  # ["location-uuid-1", ...]


class MembershipBase(BaseModel):
    """Base membership schema."""

    type: str = Field(..., description="Membership type")
    start_date: date
    end_date: date
    price: Decimal = Field(..., ge=0, decimal_places=2)
    access_rules: Optional[AccessRules] = None


class MembershipCreate(BaseModel):
    """Schema for creating a membership.

    NOTE: `price` is intentionally NOT a field here. The server derives the
    price from the membership's plan and never trusts a client-supplied value
    (WS-4b). Pydantic drops unknown extra fields by default, so a client that
    still sends `price` gets it silently ignored.
    """

    member_id: str
    plan_id: str = Field(
        ..., description="Required — price/end_date derive from the plan"
    )
    type: str
    start_date: date
    # Optional: when absent, end_date is derived from the plan duration so
    # creation and portal renewal agree on the period math.
    end_date: Optional[date] = None
    access_rules: Optional[AccessRules] = None


class MembershipUpdate(BaseModel):
    """Schema for updating a membership.

    NOTE: `price` is intentionally NOT a field (WS-4b) — the server derives it
    from the plan. Any client-supplied `price` is dropped as an unknown field.
    """

    start_date: Optional[date] = None
    end_date: Optional[date] = None
    plan_id: Optional[str] = None
    type: Optional[str] = None
    status: Optional[MembershipStatus] = None
    access_rules: Optional[AccessRules] = None


class MembershipResponse(MembershipBase):
    """Schema for membership response."""

    id: UUID
    member_id: UUID
    plan_id: Optional[UUID] = None
    status: str
    created_at: datetime
    updated_at: datetime
    # Joined member info
    member_name: Optional[str] = None
    member_id_number: Optional[str] = None
    plan_name: Optional[str] = None

    @field_serializer("id")
    def serialize_id(self, value: Any) -> str:
        """Convert UUID to string."""
        return str(value)

    @field_serializer("member_id")
    def serialize_member_id(self, value: Any) -> str:
        """Convert UUID to string."""
        return str(value)

    @field_serializer("plan_id")
    def serialize_plan_id(self, value: Any) -> Optional[str]:
        """Convert UUID to string."""
        return str(value) if value else None

    class Config:
        from_attributes = True


class MembershipListResponse(BaseModel):
    """Schema for paginated membership list."""

    total: int
    memberships: List[MembershipResponse]
