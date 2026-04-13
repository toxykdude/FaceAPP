"""
Sales/Transactions API endpoints.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, date
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
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
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
    
    return {
        "total": total,
        "transactions": transactions
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
