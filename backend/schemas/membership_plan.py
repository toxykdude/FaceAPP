"""
Pydantic schemas for Membership Plan model.
"""
from pydantic import BaseModel, Field, field_serializer
from typing import Optional, Any, List
from datetime import datetime
from decimal import Decimal

class MembershipPlanBase(BaseModel):
    name: str
    duration_days: int = Field(..., description="Duration in days")
    duration_months: int = Field(0, description="Duration in months (added to days logic if needed)")
    price: Decimal = Field(..., ge=0, decimal_places=2)
    description: Optional[str] = None
    is_active: bool = True

class MembershipPlanCreate(MembershipPlanBase):
    pass

class MembershipPlanUpdate(BaseModel):
    name: Optional[str] = None
    duration_days: Optional[int] = None
    duration_months: Optional[int] = None
    price: Optional[Decimal] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class MembershipPlanResponse(MembershipPlanBase):
    id: Any
    created_at: datetime
    updated_at: datetime
    
    @field_serializer('id')
    def serialize_id(self, value: Any) -> str:
        return str(value)
        
    class Config:
        from_attributes = True

class MembershipPlanListResponse(BaseModel):
    total: int
    plans: List[MembershipPlanResponse]
