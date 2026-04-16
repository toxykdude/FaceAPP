"""
Pydantic schemas for Membership model.
"""
from pydantic import BaseModel, Field, field_serializer
from typing import Optional, List, Any
from datetime import date, datetime
from decimal import Decimal
from models.membership import MembershipType, MembershipStatus


class AccessRules(BaseModel):
    """Access rules schema."""
    allowed_days: Optional[List[str]] = None  # ["monday", "tuesday", ...]
    time_windows: Optional[List[dict]] = None  # [{"start_time": "06:00:00", "end_time": "22:00:00"}]
    location_ids: Optional[List[str]] = None  # ["location-uuid-1", ...]


class MembershipBase(BaseModel):
    """Base membership schema."""
    type: str = Field(..., description="Membership type")
    start_date: date
    end_date: date
    price: Decimal = Field(..., ge=0, decimal_places=2)
    access_rules: Optional[AccessRules] = None


class MembershipCreate(MembershipBase):
    """Schema for creating a membership."""
    member_id: str
    plan_id: Optional[str] = None


class MembershipUpdate(BaseModel):
    """Schema for updating a membership."""
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    price: Optional[Decimal] = None
    plan_id: Optional[str] = None
    type: Optional[str] = None
    status: Optional[MembershipStatus] = None
    access_rules: Optional[AccessRules] = None


class MembershipResponse(MembershipBase):
    """Schema for membership response."""
    id: Any
    member_id: Any
    plan_id: Optional[Any] = None
    status: str
    created_at: datetime
    updated_at: datetime
    # Joined member info
    member_name: Optional[str] = None
    member_id_number: Optional[str] = None
    plan_name: Optional[str] = None
    
    @field_serializer('id')
    def serialize_id(self, value: Any) -> str:
        """Convert UUID to string."""
        return str(value)

    @field_serializer('member_id')
    def serialize_member_id(self, value: Any) -> str:
        """Convert UUID to string."""
        return str(value)

    @field_serializer('plan_id')
    def serialize_plan_id(self, value: Any) -> Optional[str]:
        """Convert UUID to string."""
        return str(value) if value else None

    class Config:
        from_attributes = True


class MembershipListResponse(BaseModel):
    """Schema for paginated membership list."""
    total: int
    memberships: List[MembershipResponse]
