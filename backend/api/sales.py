"""
Sales/Transactions API endpoints.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal
import csv
import io

from api.deps import get_db, require_staff
from models.user import User
from models.member import Member
from models.membership import Membership
from models.sale import SalesTransaction
from schemas.sale import (
    SalesTransactionCreate,
    SalesTransactionResponse,
    SalesTransactionListResponse,
    SalesReportResponse,
    DashboardResponse,
)
from services.report_window import build_report_window, DateRangeError
from services.timezone import get_app_tz

router = APIRouter(prefix="/sales", tags=["Sales"])


def _resolve_report_window(
    start_date: Optional[date], end_date: Optional[date], db: Session
) -> Optional[tuple]:
    """Resolve an optional custom report window or raise HTTP 422. Returns
    ``None`` for the preset path (no dates), or
    ``(window_start, window_end, range_start, range_end)`` for a valid range.

    The window is built in the CONFIGURED application timezone
    (``get_app_tz(db)``), not a legacy hardcoded offset, so DST-observing zones
    apply the correct per-date offset (spec: Configured-Timezone Reporting).
    """
    if start_date is None and end_date is None:
        return None
    if start_date is None or end_date is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_date and end_date must be provided together",
        )
    try:
        window = build_report_window(start_date, end_date, tz=get_app_tz(db))
    except DateRangeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    return window, start_date, end_date


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
    current_user: User = Depends(require_staff),
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
    transactions = (
        query.order_by(SalesTransaction.transaction_date.desc())
        .offset(skip)
        .limit(limit)
        .options(
            joinedload(SalesTransaction.member),
            joinedload(SalesTransaction.membership),
        )
        .all()
    )

    # Enrich with member data
    result = []
    for tx in transactions:
        member = tx.member
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
            "member_name": (
                f"{member.first_name} {member.last_name}" if member else "Unknown"
            ),
            "member_id_number": member.id_number if member else None,
        }
        result.append(tx_dict)

    return {"total": total, "transactions": result}


@router.post(
    "", response_model=SalesTransactionResponse, status_code=status.HTTP_201_CREATED
)
def create_transaction(
    transaction: SalesTransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """
    Create a new sales transaction.

    Requires staff or admin role.
    """
    # Verify member exists
    member = db.query(Member).filter(Member.id == transaction.member_id).first()
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Member not found"
        )

    # Verify membership exists if provided
    if transaction.membership_id:
        membership = (
            db.query(Membership)
            .filter(Membership.id == transaction.membership_id)
            .first()
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found"
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
        notes=transaction.notes,
    )

    db.add(db_transaction)
    db.commit()
    db.refresh(db_transaction)

    return db_transaction


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard_report(
    days: int = Query(30, ge=1, le=365),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """
    Get aggregated dashboard data for the Reports page.
    Returns revenue trends, member growth, membership distribution,
    peak hours, checkin trends, and key metrics.

    When both ``start_date`` and ``end_date`` are provided, the revenue trend is
    computed over that inclusive custom window (half-open in the application
    timezone). When neither is provided, the ``days`` preset is used.
    """
    from services.dashboard_service import DashboardService

    window = None
    range_start = range_end = None
    resolved = _resolve_report_window(start_date, end_date, db)
    if resolved is not None:
        window, range_start, range_end = resolved

    svc = DashboardService(db)
    return svc.get_dashboard(
        days=days, window=window, range_start=range_start, range_end=range_end
    )


@router.get("/report/summary", response_model=SalesReportResponse)
def get_sales_report(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """
    Get sales report summary.

    - **start_date**: Report start date (optional, inclusive)
    - **end_date**: Report end date (optional, inclusive)

    When both are provided, data is restricted to the half-open window
    ``[start_date 00:00, (end_date + 1) 00:00)`` in the application timezone.
    A reversed range (start after end) or a partial range (only one date) is
    rejected with HTTP 422.
    """
    query = db.query(SalesTransaction)

    # Filter by half-open custom date window (422 on partial/reversed range).
    resolved = _resolve_report_window(start_date, end_date, db)
    if resolved is not None:
        (window_start, window_end), _rs, _re = resolved
        query = query.filter(
            SalesTransaction.transaction_date >= window_start,
            SalesTransaction.transaction_date < window_end,
        )

    # Get total revenue
    total_revenue = query.with_entities(
        func.sum(SalesTransaction.amount)
    ).scalar() or Decimal(0)

    # Get total transactions
    total_transactions = query.count()

    # Get transactions by payment method
    transactions_by_method = {}
    revenue_by_method = {}

    for method in ["cash", "card", "transfer"]:
        method_query = query.filter(SalesTransaction.payment_method == method)
        transactions_by_method[method] = method_query.count()
        revenue_by_method[method] = float(
            method_query.with_entities(func.sum(SalesTransaction.amount)).scalar()
            or Decimal(0)
        )

    return {
        "total_revenue": total_revenue,
        "total_transactions": total_transactions,
        "transactions_by_method": transactions_by_method,
        "revenue_by_method": revenue_by_method,
    }


@router.get("/report/export")
def export_sales_report(
    days: int = Query(30, ge=1, le=365),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """Stream a server-side CSV of sales transactions for the selected range.

    Reuses ``_resolve_report_window`` so the CSV applies the SAME half-open
    configured-timezone window as ``/report/summary`` (spec: Server-Side CSV
    Report Export). When no dates are given the preset ``days`` window is used.
    The ``transaction_date`` column is rendered in the configured timezone
    (date+time) so the file matches what admins see on screen.
    """
    from services.timezone import get_app_tz, utc_to_local

    tz = get_app_tz(db)

    query = db.query(SalesTransaction).options(
        joinedload(SalesTransaction.member),
        joinedload(SalesTransaction.membership),
    )

    resolved = _resolve_report_window(start_date, end_date, db)
    if resolved is not None:
        (window_start, window_end), range_start, range_end = resolved
        query = query.filter(
            SalesTransaction.transaction_date >= window_start,
            SalesTransaction.transaction_date < window_end,
        )
        range_label = f"{range_start.isoformat()}_to_{range_end.isoformat()}"
    else:
        now = datetime.now(timezone.utc)
        period_start = now - timedelta(days=days)
        query = query.filter(SalesTransaction.transaction_date >= period_start)
        range_label = f"last_{days}_days"

    transactions = query.order_by(SalesTransaction.transaction_date.desc()).all()

    header = [
        "invoice_number",
        "member_name",
        "member_id_number",
        "amount",
        "payment_method",
        "transaction_date",
        "notes",
    ]

    def _row(tx: SalesTransaction) -> list:
        member = tx.member
        member_name = (
            f"{member.first_name} {member.last_name}" if member else "Unknown"
        )
        local_dt = utc_to_local(tx.transaction_date, tz)
        return [
            tx.invoice_number or "",
            member_name,
            (member.id_number if member else ""),
            f"{tx.amount:.2f}",
            tx.payment_method or "",
            local_dt.strftime("%Y-%m-%d %H:%M"),
            tx.notes or "",
        ]

    def _stream():
        buf = io.StringIO()
        # Excel-friendly UTF-8 BOM so accented names render correctly.
        buf.write("\ufeff")
        writer = csv.writer(buf)
        writer.writerow(header)
        yield buf.getvalue()
        for tx in transactions:
            row_buf = io.StringIO()
            csv.writer(row_buf).writerow(_row(tx))
            yield row_buf.getvalue()

    filename = f"sales_report_{range_label}.csv"
    return StreamingResponse(
        _stream(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{transaction_id}", response_model=SalesTransactionResponse)
def get_transaction(
    transaction_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """
    Get transaction by ID.
    """
    transaction = (
        db.query(SalesTransaction).filter(SalesTransaction.id == transaction_id).first()
    )

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found"
        )

    return transaction
