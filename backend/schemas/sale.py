"""
Pydantic schemas for Sales/Transactions.
"""
from pydantic import BaseModel, Field, field_serializer
from typing import Optional, List, Any
from datetime import datetime
from decimal import Decimal


class SalesTransactionBase(BaseModel):
    """Base sales transaction schema."""
    member_id: str
    membership_id: Optional[str] = None
    amount: Decimal = Field(..., ge=0, decimal_places=2)
    payment_method: str = Field(..., description="Payment method: cash, card, transfer")
    notes: Optional[str] = None


class SalesTransactionCreate(SalesTransactionBase):
    """Schema for creating a sales transaction."""
    pass


class SalesTransactionResponse(SalesTransactionBase):
    """Schema for sales transaction response."""
    id: Any
    member_id: Any
    membership_id: Optional[Any] = None
    invoice_number: str
    transaction_date: datetime
    created_at: datetime
    
    @field_serializer('id', 'member_id', 'membership_id')
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
