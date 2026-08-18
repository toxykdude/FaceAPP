"""
Pydantic schemas for Member Portal authentication and data.
"""

from decimal import Decimal
from typing import Optional, List, Any
from datetime import date, datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, field_validator, field_serializer


class MemberLoginRequest(BaseModel):
    """Schema for member login (phone-based)."""

    phone: str

    @field_validator("phone")
    @classmethod
    def strip_phone(cls, v: str) -> str:
        return v.strip()


class MemberVerifyRequest(BaseModel):
    """Schema for member PIN verification."""

    phone: str
    pin: str = Field(..., pattern=r"^\d{6}$", description="6-digit PIN")


class MemberPortalResponse(BaseModel):
    """Schema for member data in portal responses."""

    id: UUID
    first_name: str
    last_name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    status: str
    facial_data_enrolled: bool

    @field_serializer("id")
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

    id: UUID
    type: str
    plan_name: Optional[str] = None
    start_date: date
    end_date: date
    price: Any
    status: str
    days_remaining: int

    @field_serializer("id")
    def serialize_id(self, value: Any) -> str:
        """Convert UUID to string."""
        return str(value)

    @field_serializer("price")
    def serialize_price(self, value: Any) -> float:
        """Convert Decimal to float for JSON."""
        return float(value)

    class Config:
        from_attributes = True


class PaymentHistoryItem(BaseModel):
    """Schema for payment history item in portal."""

    id: UUID
    invoice_number: Optional[str] = None
    amount: Any
    payment_method: Optional[str] = None
    transaction_date: datetime

    @field_serializer("id")
    def serialize_id(self, value: Any) -> str:
        """Convert UUID to string."""
        return str(value)

    @field_serializer("amount")
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

    id: UUID
    name: str
    duration_days: int
    duration_months: Optional[int] = None
    price: Any
    description: Optional[str] = None

    @field_serializer("id")
    def serialize_id(self, value: Any) -> str:
        """Convert UUID to string."""
        return str(value)

    @field_serializer("price")
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


class PortalPendingPaymentRequest(BaseModel):
    """Schema for storing a pending payment (JWT member path, pre-widget).

    ``amount`` and ``member_id`` are accepted for backward compatibility with
    the deployed relay but IGNORED: the member comes from the JWT and the
    amount from the server-side plan price.
    """

    plan_id: str
    wompi_reference: str
    member_id: Optional[str] = None
    wompi_transaction_id: Optional[str] = None
    amount: Optional[Decimal] = None


class PortalGuestPendingPaymentRequest(BaseModel):
    """Guest checkout pending record (no JWT — design D10).

    The guest path carries identity instead of a member binding: the
    webhook's guest branch later resolves or creates the member from
    ``guest_phone`` (canonical 57+10). The ``wompi_reference`` pattern is
    the Pages signature format — anything else is reference stuffing and
    is rejected before touching Redis. There is no ``amount`` field at
    all: the server resolves the plan price from the database.
    """

    guest_name: str = Field(..., min_length=2, max_length=200)
    guest_phone: str = Field(..., min_length=7, max_length=30)
    guest_email: EmailStr
    plan_id: str
    wompi_reference: str = Field(
        ...,
        pattern=r"^PH-[a-z0-9-]+-\d{10}-[a-f0-9]{6}$",
    )

    @field_validator("guest_name")
    @classmethod
    def normalize_guest_name(cls, v: str) -> str:
        """Collapse whitespace runs; a name must survive stripping."""
        name = " ".join(v.split())
        if len(name) < 2:
            raise ValueError("guest_name must contain at least 2 letters")
        return name


class PortalWebhookRenewRequest(BaseModel):
    """Schema v2 for webhook-triggered renewal (design D4/D9).

    Server-to-server only (HMAC-verified). ``wompi_reference``,
    ``wompi_transaction_id`` and ``amount_in_cents`` are REQUIRED — the
    deploy-gap contract: an old relay omitting ``amount_in_cents`` is
    rejected loudly (422) instead of provisioning an unverified amount.

    ``plan_id`` / ``member_id`` / ``amount`` are accepted but IGNORED: the
    Redis pending record is the only authoritative source (it is written by
    the server, never by the client).
    """

    wompi_reference: str = Field(..., min_length=1)
    wompi_transaction_id: str = Field(..., min_length=1)
    amount_in_cents: int
    plan_id: Optional[str] = None
    member_id: Optional[str] = None
    amount: Optional[Decimal] = None
