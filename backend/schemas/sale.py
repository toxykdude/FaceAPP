"""
Pydantic schemas for Sales/Transactions.
"""

from pydantic import BaseModel, Field, field_serializer
from typing import Optional, List, Any
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from models.sale import PaymentMethod


class SalesTransactionBase(BaseModel):
    """Base sales transaction schema."""

    member_id: str
    membership_id: Optional[str] = None
    amount: Decimal = Field(..., ge=0, decimal_places=2)
    payment_method: PaymentMethod = Field(..., description="Payment method")
    notes: Optional[str] = None


class SalesTransactionCreate(SalesTransactionBase):
    """Schema for creating a sales transaction."""

    pass


class SalesTransactionResponse(SalesTransactionBase):
    """Schema for sales transaction response."""

    id: UUID
    member_id: UUID
    membership_id: Optional[UUID] = None
    invoice_number: Optional[str] = None
    transaction_date: datetime
    created_at: datetime
    member_name: Optional[str] = None
    member_id_number: Optional[str] = None

    @field_serializer("id", "member_id", "membership_id")
    def serialize_uuids(self, value: Any) -> Optional[str]:
        """Convert UUID to string."""
        if value is None:
            return None
        return str(value)

    class Config:
        from_attributes = True


class SalesTransactionListResponse(BaseModel):
    """Schema for paginated sales transaction list."""

    total: int
    transactions: List[SalesTransactionResponse]


class SalesReportResponse(BaseModel):
    """Schema for sales report."""

    total_revenue: Decimal
    total_transactions: int
    transactions_by_method: dict
    revenue_by_method: dict


class DashboardResponse(BaseModel):
    """Schema for dashboard aggregated data."""

    revenue_trend: List[Any]
    member_growth: List[Any]
    membership_distribution: List[Any]
    peak_hours: List[Any]
    checkin_trend: List[Any]
    new_signups: Any
    active_vs_expired: Any
    checkins_today: int
    checkins_week: int
    revenue_change_pct: float
