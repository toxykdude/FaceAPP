"""
Membership model for membership plans and subscriptions.
"""

import uuid
from datetime import datetime, date, timezone
from decimal import Decimal
from sqlalchemy import (
    Column,
    String,
    DateTime,
    Date,
    Numeric,
    ForeignKey,
    Enum,
    Integer,
    Boolean,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import enum
import uuid
from datetime import datetime, date, timezone

from core.database import Base


class MembershipType(str, enum.Enum):
    """Membership type enum."""

    MONTHLY = "monthly"
    ANNUAL = "annual"
    PREPAID = "prepaid"
    DAILY = "daily"


class MembershipStatus(str, enum.Enum):
    """Membership status enum."""

    ACTIVE = "active"
    EXPIRED = "expired"
    SUSPENDED = "suspended"


class PaymentStatus(str, enum.Enum):
    """How much of a membership's price has actually been collected.

    Derived, never stored: the sales transactions recorded against a
    membership are the only source of truth for money received, so a
    separate column could only drift away from the ledger.
    """

    PAID = "paid"
    PARTIAL = "partial"
    PENDING = "pending"


class MembershipPlan(Base):
    """Membership Plan model for reusable templates."""

    __tablename__ = "membership_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    duration_days = Column(Integer, nullable=False)
    duration_months = Column(Integer, default=0)  # User asked for days, months
    price = Column(Numeric(10, 2), nullable=False)
    description = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)

    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return f"<MembershipPlan {self.name}>"


class Membership(Base):
    """Membership model for member subscriptions."""

    __tablename__ = "memberships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id = Column(
        UUID(as_uuid=True),
        ForeignKey("members.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Optional link to plan
    plan_id = Column(
        UUID(as_uuid=True), ForeignKey("membership_plans.id"), nullable=True
    )

    type = Column(String(50), nullable=False)  # e.g. "Monthly", or plan name
    start_date = Column(Date, nullable=False, index=True)
    end_date = Column(Date, nullable=False, index=True)
    price = Column(Numeric(10, 2), nullable=False)
    status = Column(
        String(20), nullable=False, default=MembershipStatus.ACTIVE.value, index=True
    )

    # Access rules stored as JSONB
    access_rules = Column(JSONB, nullable=True, default={})

    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    member = relationship("Member", back_populates="memberships")
    plan = relationship("MembershipPlan")
    sales_transactions = relationship("SalesTransaction", back_populates="membership")

    def __repr__(self):
        return f"<Membership {self.type} for Member {self.member_id} ({self.status})>"

    @property
    def is_active(self):
        """Check if membership is currently active."""
        today = date.today()
        return (
            self.status == MembershipStatus.ACTIVE.value
            and self.start_date <= today <= self.end_date
        )

    @property
    def is_expired(self):
        """Check if membership has expired."""
        return date.today() > self.end_date

    @property
    def amount_paid(self) -> Decimal:
        """Money actually collected for this membership.

        Summed from the linked sales transactions rather than stored, so a
        later instalment recorded against the same membership updates the
        balance with no write to this row. Callers that serialize many
        memberships should eager-load ``sales_transactions`` to avoid N+1
        queries.
        """
        return sum(
            (Decimal(str(tx.amount)) for tx in self.sales_transactions),
            Decimal("0.00"),
        )

    @property
    def amount_due(self) -> Decimal:
        """Outstanding balance, floored at zero.

        An overpayment is never reported as a negative debt — the kiosk and
        the admin UI both read this as "how much to collect", and a negative
        figure there would render as a nonsense charge.
        """
        outstanding = Decimal(str(self.price)) - self.amount_paid
        return outstanding if outstanding > Decimal("0.00") else Decimal("0.00")

    @property
    def payment_status(self) -> str:
        """``paid`` / ``partial`` / ``pending`` for this membership.

        A zero-priced membership is ``paid``: nothing is owed, so there is
        nothing to warn anyone about.
        """
        if self.amount_due <= Decimal("0.00"):
            return PaymentStatus.PAID.value
        if self.amount_paid > Decimal("0.00"):
            return PaymentStatus.PARTIAL.value
        return PaymentStatus.PENDING.value
