"""
Member Portal endpoints — member self-service.
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.deps import get_db, get_current_member
from models.member import Member
from models.membership import Membership, MembershipPlan
from models.sale import SalesTransaction
from schemas.portal import (
    PortalMeResponse,
    PortalPlanResponse,
    PortalRenewRequest,
    PortalRenewResponse,
    ActiveMembershipResponse,
    PaymentHistoryItem,
)

router = APIRouter(prefix="/portal", tags=["Member Portal"])


@router.get("/me", response_model=PortalMeResponse)
def portal_me(
    member: Member = Depends(get_current_member),
    db: Session = Depends(get_db),
):
    """
    Get current member's profile, active membership, and recent payments.
    """
    today = date.today()

    # Load active membership
    active_membership = db.query(Membership).filter(
        Membership.member_id == str(member.id),
        Membership.status == "active",
        Membership.start_date <= today,
        Membership.end_date >= today,
    ).order_by(Membership.end_date.desc()).first()

    active_membership_response = None
    if active_membership:
        # Get plan name
        plan_name = None
        if active_membership.plan_id:
            plan = db.query(MembershipPlan).filter(
                MembershipPlan.id == active_membership.plan_id
            ).first()
            plan_name = plan.name if plan else None

        active_membership_response = ActiveMembershipResponse(
            id=active_membership.id,
            type=active_membership.type,
            plan_name=plan_name,
            start_date=active_membership.start_date,
            end_date=active_membership.end_date,
            price=active_membership.price,
            status=active_membership.status,
            days_remaining=(active_membership.end_date - today).days,
        )

    # Load recent payments (last 10)
    recent_payments = (
        db.query(SalesTransaction)
        .filter(SalesTransaction.member_id == str(member.id))
        .order_by(SalesTransaction.transaction_date.desc())
        .limit(10)
        .all()
    )

    return PortalMeResponse(
        member=member,
        active_membership=active_membership_response,
        recent_payments=recent_payments,
    )


@router.get("/plans", response_model=list[PortalPlanResponse])
def portal_plans(
    db: Session = Depends(get_db),
):
    """
    Get all active membership plans (public — no auth required).
    """
    plans = db.query(MembershipPlan).filter(MembershipPlan.is_active == True).all()
    return plans


@router.post("/renew", response_model=PortalRenewResponse)
def portal_renew(
    request: PortalRenewRequest,
    member: Member = Depends(get_current_member),
    db: Session = Depends(get_db),
):
    """
    Renew membership using a Wompi payment reference.

    Validates the plan, creates a new membership and sales transaction.
    """
    # Verify plan exists and is active
    plan = db.query(MembershipPlan).filter(
        MembershipPlan.id == request.plan_id,
        MembershipPlan.is_active == True,
    ).first()

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan no encontrado o inactivo",
        )

    today = date.today()

    # Check for existing active membership
    active_membership = db.query(Membership).filter(
        Membership.member_id == str(member.id),
        Membership.status == "active",
        Membership.start_date <= today,
        Membership.end_date >= today,
    ).order_by(Membership.end_date.desc()).first()

    # Calculate dates — extend from current end_date if active, otherwise start today
    start_date = today
    if active_membership and active_membership.end_date >= today:
        start_date = active_membership.end_date + timedelta(days=1)

    end_date = start_date + timedelta(days=plan.duration_days)

    # Create membership
    new_membership = Membership(
        member_id=str(member.id),
        plan_id=plan.id,
        type=plan.name,
        start_date=start_date,
        end_date=end_date,
        price=Decimal(str(request.amount)),
        status="active",
    )
    db.add(new_membership)
    db.flush()  # Get the ID before creating the transaction

    # Generate invoice number
    invoice_number = f"REN-{date.today().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

    # Create sales transaction
    transaction = SalesTransaction(
        member_id=str(member.id),
        membership_id=new_membership.id,
        amount=Decimal(str(request.amount)),
        payment_method="card",
        invoice_number=invoice_number,
        notes=f"Wompi ref: {request.wompi_reference}",
    )
    db.add(transaction)
    db.commit()
    db.refresh(new_membership)
    db.refresh(transaction)

    # Build plan name
    plan_name = plan.name if plan else None

    return PortalRenewResponse(
        membership=ActiveMembershipResponse(
            id=new_membership.id,
            type=new_membership.type,
            plan_name=plan_name,
            start_date=new_membership.start_date,
            end_date=new_membership.end_date,
            price=new_membership.price,
            status=new_membership.status,
            days_remaining=(new_membership.end_date - today).days,
        ),
        transaction=transaction,
    )
