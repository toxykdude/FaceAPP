"""
Pydantic schemas for Member Portal authentication and data.
"""
from decimal import Decimal
from typing import Optional, List, Any
from datetime import date, datetime
from pydantic import BaseModel, Field, field_validator, field_serializer


class MemberLoginRequest(BaseModel):
    """Schema for member login (phone-based)."""
    phone: str

    @field_validator('phone')
    @classmethod
    def strip_phone(cls, v: str) -> str:
        return v.strip()


class MemberVerifyRequest(BaseModel):
    """Schema for member PIN verification."""
    phone: str
    pin: str = Field(..., pattern=r'^\d{6}$', description="6-digit PIN")


class MemberPortalResponse(BaseModel):
    """Schema for member data in portal responses."""
    id: Any
    first_name: str
    last_name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    status: str
    facial_data_enrolled: bool

    @field_serializer('id')
    def serialize_id(self, value: Any) -> str:
        """Convert UUID to string."""
        return str(value)

    class Config:
        from_attributes = True


class MemberPortalToken(BaseModel):
    """Schema for member portal authentication response."""
    access_token: str
    token_type: str = "bearer"
    member: MemberPortalResponse


class ActiveMembershipResponse(BaseModel):
    """Schema for active membership data in portal."""
    id: Any
    type: str
    plan_name: Optional[str] = None
    start_date: date
    end_date: date
    price: Any
    status: str
    days_remaining: int

    @field_serializer('id')
    def serialize_id(self, value: Any) -> str:
        """Convert UUID to string."""
        return str(value)

    @field_serializer('price')
    def serialize_price(self, value: Any) -> float:
        """Convert Decimal to float for JSON."""
        return float(value)

    class Config:
        from_attributes = True


class PaymentHistoryItem(BaseModel):
    """Schema for payment history item in portal."""
    id: Any
    invoice_number: str
    amount: Any
    payment_method: str
    transaction_date: datetime

    @field_serializer('id')
    def serialize_id(self, value: Any) -> str:
        """Convert UUID to string."""
        return str(value)

    @field_serializer('amount')
    def serialize_amount(self, value: Any) -> float:
        """Convert Decimal to float for JSON."""
        return float(value)

    class Config:
        from_attributes = True


class PortalMeResponse(BaseModel):
    """Schema for /portal/me endpoint response."""
    member: MemberPortalResponse
    active_membership: Optional[ActiveMembershipResponse] = None
    recent_payments: List[PaymentHistoryItem] = []


class PortalPlanResponse(BaseModel):
    """Schema for membership plan in portal (public)."""
    id: Any
    name: str
    duration_days: int
    duration_months: Optional[int] = None
    price: Any
    description: Optional[str] = None

    @field_serializer('id')
    def serialize_id(self, value: Any) -> str:
        """Convert UUID to string."""
        return str(value)

    @field_serializer('price')
    def serialize_price(self, value: Any) -> float:
        """Convert Decimal to float for JSON."""
        return float(value)

    class Config:
        from_attributes = True


class PortalRenewRequest(BaseModel):
    """Schema for membership renewal request from portal."""
    plan_id: str
    wompi_reference: str
    amount: Decimal


class PortalRenewResponse(BaseModel):
    """Schema for membership renewal response."""
    membership: ActiveMembershipResponse
    transaction: PaymentHistoryItem
