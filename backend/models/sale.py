"""
Sales transaction model for payment tracking.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Numeric, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from core.database import Base


class PaymentMethod(str, enum.Enum):
    """Payment method enum."""
    CASH = "cash"
    CARD = "card"
    TRANSFER = "transfer"


class SalesTransaction(Base):
    """Sales transaction model for payment records."""
    
    __tablename__ = "sales_transactions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id = Column(UUID(as_uuid=True), ForeignKey("members.id"), nullable=False, index=True)
    membership_id = Column(UUID(as_uuid=True), ForeignKey("memberships.id"), nullable=True)
    
    amount = Column(Numeric(10, 2), nullable=False)
    payment_method = Column(String(20), nullable=False)
    transaction_date = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    invoice_number = Column(String(50), unique=True, nullable=False, index=True)
    notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    member = relationship("Member", back_populates="sales_transactions")
    membership = relationship("Membership", back_populates="sales_transactions")
    
    def __repr__(self):
        return f"<SalesTransaction {self.invoice_number} - ${self.amount}>"
