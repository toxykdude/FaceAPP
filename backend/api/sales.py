"""
Sales/Transactions API endpoints.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, date, timezone, timedelta
from collections import defaultdict
from decimal import Decimal

from api.deps import get_db, require_staff
from models.user import User
from models.member import Member
from models.membership import Membership
from models.sale import SalesTransaction
from schemas.sale import (
    SalesTransactionCreate,
    SalesTransactionResponse,
    SalesTransactionListResponse,
    SalesReportResponse
)

router = APIRouter(prefix="/sales", tags=["Sales"])


def generate_invoice_number() -> str:
    """Generate unique invoice number."""
    import uuid
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    short_id = uuid.uuid4().hex[:6]
    return f"INV-{timestamp}-{short_id}"


@router.get("", response_model=SalesTransactionListResponse)
def list_transactions(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    member_id: Optional[str] = None,
    payment_method: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff)
):
    """
    List all sales transactions with pagination and filtering.
    
    - **skip**: Number of records to skip
    - **limit**: Maximum number of records to return
    - **member_id**: Filter by member ID
    - **payment_method**: Filter by payment method
    - **start_date**: Filter transactions from this date
    - **end_date**: Filter transactions until this date
    """
    query = db.query(SalesTransaction)
    
    # Filter by member
    if member_id:
        query = query.filter(SalesTransaction.member_id == member_id)
    
    # Filter by payment method
    if payment_method:
        query = query.filter(SalesTransaction.payment_method == payment_method)
    
    # Filter by date range
    if start_date:
        query = query.filter(SalesTransaction.transaction_date >= start_date)
    if end_date:
        query = query.filter(SalesTransaction.transaction_date <= end_date)
    
    # Get total count
    total = query.count()
    
    # Get paginated results
    transactions = query.order_by(SalesTransaction.transaction_date.desc()).offset(skip).limit(limit).all()
    
    # Enrich with member data
    result = []
    for tx in transactions:
        member = db.query(Member).filter(Member.id == tx.member_id).first()
        tx_dict = {
            "id": str(tx.id),
            "member_id": str(tx.member_id),
            "membership_id": str(tx.membership_id) if tx.membership_id else None,
            "amount": tx.amount,
            "payment_method": tx.payment_method,
            "invoice_number": tx.invoice_number,
            "notes": tx.notes,
            "transaction_date": tx.transaction_date,
            "created_at": tx.created_at,
            "member_name": f"{member.first_name} {member.last_name}" if member else "Unknown",
            "member_id_number": member.id_number if member else None,
        }
        result.append(tx_dict)

    return {
        "total": total,
        "transactions": result
    }


@router.post("", response_model=SalesTransactionResponse, status_code=status.HTTP_201_CREATED)
def create_transaction(
    transaction: SalesTransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff)
):
    """
    Create a new sales transaction.
    
    Requires staff or admin role.
    """
    # Verify member exists
    member = db.query(Member).filter(Member.id == transaction.member_id).first()
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found"
        )
    
    # Verify membership exists if provided
    if transaction.membership_id:
        membership = db.query(Membership).filter(Membership.id == transaction.membership_id).first()
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Membership not found"
            )
    
    # Generate invoice number
    invoice_number = generate_invoice_number()
    
    # Create transaction
    db_transaction = SalesTransaction(
        member_id=transaction.member_id,
        membership_id=transaction.membership_id,
        amount=transaction.amount,
        payment_method=transaction.payment_method,
        invoice_number=invoice_number,
        notes=transaction.notes
    )
    
    db.add(db_transaction)
    db.commit()
    db.refresh(db_transaction)
    
    return db_transaction




@router.get("/dashboard")
def get_dashboard_report(
    days: int = Query(30, ge=7, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """
    Get aggregated dashboard data for the Reports page.
    Returns revenue trends, member growth, membership distribution,
    peak hours, checkin trends, and key metrics.
    """
    from models.event import AccessEvent
    from sqlalchemy import extract

    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # 1. Revenue Trend - daily sales for last N days
    period_start = now - timedelta(days=days)
    sales = db.query(SalesTransaction).filter(
        SalesTransaction.transaction_date >= period_start
    ).all()

    daily_revenue = defaultdict(float)
    for s in sales:
        key = s.transaction_date.strftime("%Y-%m-%d")
        daily_revenue[key] += float(s.amount)

    revenue_trend = []
    for i in range(days):
        d = (now - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        revenue_trend.append({"date": d, "amount": daily_revenue.get(d, 0)})

    # 2. Member Growth - monthly new members for last 6 months
    member_growth = []
    for i in range(5, -1, -1):
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        m_start = now.replace(year=y, month=m, day=1, hour=0, minute=0, second=0, microsecond=0)
        if i == 0:
            m_end = now
        else:
            nm = m + 1
            ny = y
            if nm > 12:
                nm = 1
                ny += 1
            m_end = m_start.replace(month=nm, year=ny)

        count = db.query(Member).filter(
            Member.created_at >= m_start,
            Member.created_at < m_end
        ).count()
        member_growth.append({"month": m_start.strftime("%b %Y"), "count": count})

    # 3. Membership Distribution - count by plan type
    memberships = db.query(
        Membership.type, func.count(Membership.id)
    ).filter(
        Membership.status == "active"
    ).group_by(Membership.type).all()

    membership_distribution = [{"plan": name or "Unknown", "count": count} for name, count in memberships]

    # 4. Peak Hours - all-time check-ins by hour
    all_events = db.query(AccessEvent).filter(
        AccessEvent.access_granted == True,
    ).all()

    hourly = defaultdict(int)
    for e in all_events:
        hour = e.timestamp.hour if e.timestamp else 0
        hourly[hour] += 1

    peak_hours = []
    for h in range(6, 23):
        label = f"{h % 12 or 12}{'AM' if h < 12 else 'PM'}"
        peak_hours.append({"hour": h, "label": label, "checkins": hourly.get(h, 0)})

    # 5. Checkin Trend - daily check-ins for the period
    daily_checkins_events = db.query(AccessEvent).filter(
        AccessEvent.access_granted == True,
        AccessEvent.timestamp >= period_start
    ).all()

    daily_checkins = defaultdict(int)
    for e in daily_checkins_events:
        key = e.timestamp.strftime("%Y-%m-%d")
        daily_checkins[key] += 1

    checkin_trend = []
    for i in range(days):
        d = (now - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        checkin_trend.append({"date": d, "count": daily_checkins.get(d, 0)})

    # 6. New signups this month vs last month
    last_month_start = (month_start - timedelta(days=1)).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )

    new_this_month = db.query(Member).filter(Member.created_at >= month_start).count()
    new_last_month = db.query(Member).filter(
        Member.created_at >= last_month_start,
        Member.created_at < month_start
    ).count()

    signup_change = ((new_this_month - new_last_month) / new_last_month * 100) if new_last_month > 0 else 0

    # 7. Active vs Expired memberships
    active_count = db.query(Membership).filter(Membership.status == "active").count()
    expired_count = db.query(Membership).filter(Membership.status == "expired").count()

    # 8. Check-ins today and this week
    checkins_today = db.query(AccessEvent).filter(
        AccessEvent.access_granted == True,
        AccessEvent.timestamp >= today_start
    ).count()

    checkins_week = db.query(AccessEvent).filter(
        AccessEvent.access_granted == True,
        AccessEvent.timestamp >= week_start
    ).count()

    # 9. Revenue change (this month vs last month)
    rev_this_month = sum(float(s.amount) for s in sales if s.transaction_date >= month_start)
    rev_last_month_sales = db.query(SalesTransaction).filter(
        SalesTransaction.transaction_date >= last_month_start,
        SalesTransaction.transaction_date < month_start
    ).all()
    rev_last_month = sum(float(s.amount) for s in rev_last_month_sales)
    revenue_change = ((rev_this_month - rev_last_month) / rev_last_month * 100) if rev_last_month > 0 else 0

    return {
        "revenue_trend": revenue_trend,
        "member_growth": member_growth,
        "membership_distribution": membership_distribution,
        "peak_hours": peak_hours,
        "checkin_trend": checkin_trend,
        "new_signups": {"this_month": new_this_month, "last_month": new_last_month, "change_pct": round(signup_change, 1)},
        "active_vs_expired": {"active": active_count, "expired": expired_count},
        "checkins_today": checkins_today,
        "checkins_week": checkins_week,
        "revenue_change_pct": round(revenue_change, 1),
    }

@router.get("/{transaction_id}", response_model=SalesTransactionResponse)
def get_transaction(
    transaction_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff)
):
    """
    Get transaction by ID.
    """
    transaction = db.query(SalesTransaction).filter(SalesTransaction.id == transaction_id).first()
    
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found"
        )
    
    return transaction


@router.get("/report/summary", response_model=SalesReportResponse)
def get_sales_report(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff)
):
    """
    Get sales report summary.
    
    - **start_date**: Report start date (optional)
    - **end_date**: Report end date (optional)
    """
    query = db.query(SalesTransaction)
    
    # Filter by date range
    if start_date:
        query = query.filter(SalesTransaction.transaction_date >= start_date)
    if end_date:
        query = query.filter(SalesTransaction.transaction_date <= end_date)
    
    # Get total revenue
    total_revenue = query.with_entities(func.sum(SalesTransaction.amount)).scalar() or Decimal(0)
    
    # Get total transactions
    total_transactions = query.count()
    
    # Get transactions by payment method
    transactions_by_method = {}
    revenue_by_method = {}
    
    for method in ["cash", "card", "transfer"]:
        method_query = query.filter(SalesTransaction.payment_method == method)
        transactions_by_method[method] = method_query.count()
        revenue_by_method[method] = float(method_query.with_entities(func.sum(SalesTransaction.amount)).scalar() or Decimal(0))
    
    return {
        "total_revenue": total_revenue,
        "total_transactions": total_transactions,
        "transactions_by_method": transactions_by_method,
        "revenue_by_method": revenue_by_method
    }
