"""
Member Portal endpoints — member self-service.
"""
import hashlib
import hmac
import uuid
from datetime import date, timedelta
from decimal import Decimal
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from api.deps import get_db, get_current_member, get_portal_session
from models.member import Member
from models.membership import Membership, MembershipPlan
from models.sale import SalesTransaction
from schemas.portal import (
    PortalMeResponse,
    PortalPlanResponse,
    PortalRenewRequest,
    PortalRenewResponse,
    PortalWebhookRenewRequest,
    ActiveMembershipResponse,
    PaymentHistoryItem,
)

router = APIRouter(prefix="/portal", tags=["Member Portal"])


@router.get("/me", response_model=PortalMeResponse)
def portal_me(
    member: Member = Depends(get_current_member),
    db: Session = Depends(get_portal_session),
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
    db: Session = Depends(get_portal_session),
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


def verify_wompi_signature(request_body: bytes, signature_header: str) -> bool:
    """
    Verify Wompi webhook HMAC-SHA256 signature.
    The signature is computed from the raw request body using the integrity secret.
    """
    from core.config import settings

    if not settings.WOMPI_INTEGRITY_SECRET:
        import logging
        logging.getLogger(__name__).error("WOMPI_INTEGRITY_SECRET not configured — webhook verification disabled")
        return False

    expected = hmac.new(
        settings.WOMPI_INTEGRITY_SECRET.encode(),
        request_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature_header)


@router.post("/webhook-renew")
async def portal_webhook_renew(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Renew membership from Wompi webhook — no JWT required.
    Called server-to-server by the Cloudflare Pages Function webhook.
    Verified via HMAC-SHA256 signature from Wompi.

    Uses plan_id + member_id from the request (stored in Redis by the
    pending-payment endpoint and passed through by the webhook handler).
    """
    import logging
    import json
    logger = logging.getLogger(__name__)

    # Verify Wompi signature
    signature = request.headers.get("X-Signature", "")
    body = await request.body()

    if not verify_wompi_signature(body, signature):
        logger.warning("Webhook renew: invalid or missing Wompi signature")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )

    # Parse the body as the expected schema
    try:
        body_data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON body",
        )

    request_data = PortalWebhookRenewRequest(**body_data)

    # Verify plan exists and is active
    plan = db.query(MembershipPlan).filter(
        MembershipPlan.id == request_data.plan_id,
        MembershipPlan.is_active == True,
    ).first()

    if not plan:
        logger.error(f"Webhook renew: plan {request_data.plan_id} not found or inactive")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan no encontrado o inactivo",
        )

    # Verify member exists
    member = db.query(Member).filter(Member.id == request_data.member_id).first()
    if not member:
        logger.error(f"Webhook renew: member {request_data.member_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Miembro no encontrado",
        )

    # Idempotency check: avoid duplicate memberships for the same Wompi reference
    existing_tx = db.query(SalesTransaction).filter(
        SalesTransaction.notes.like(f"%{request_data.wompi_reference}%")
    ).first()
    if existing_tx:
        logger.info(f"Webhook renew: already processed reference {request_data.wompi_reference}, skipping")
        return {"status": "already_processed", "membership_id": str(existing_tx.membership_id)}

    today = date.today()

    # Check for existing active membership — extend from current end_date
    active_membership = db.query(Membership).filter(
        Membership.member_id == str(member.id),
        Membership.status == "active",
        Membership.start_date <= today,
        Membership.end_date >= today,
    ).order_by(Membership.end_date.desc()).first()

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
        price=Decimal(str(request_data.amount)),
        status="active",
    )
    db.add(new_membership)
    db.flush()

    # Generate invoice number
    invoice_number = f"WOM-{today.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

    # Create sales transaction
    transaction = SalesTransaction(
        member_id=str(member.id),
        membership_id=new_membership.id,
        amount=Decimal(str(request_data.amount)),
        payment_method="card",
        invoice_number=invoice_number,
        notes=f"Wompi ref: {request_data.wompi_reference} | Wompi tx: {request_data.wompi_transaction_id}",
    )
    db.add(transaction)
    db.commit()
    db.refresh(new_membership)
    db.refresh(transaction)

    logger.info(
        f"Webhook renew: created membership {new_membership.id} for member {member.id}, "
        f"plan {plan.name}, {start_date} to {end_date}"
    )

    return {
        "status": "success",
        "membership_id": str(new_membership.id),
        "start_date": str(start_date),
        "end_date": str(end_date),
        "plan_name": plan.name,
    }


@router.post("/pending-payment")
def portal_pending_payment(
    request: PortalWebhookRenewRequest,
    member: Member = Depends(get_current_member),
):
    """
    Store pending payment info in Redis BEFORE opening Wompi widget.
    The webhook later reads this to activate membership.
    """
    import redis
    import json
    from core.config import settings
    import logging
    logger = logging.getLogger(__name__)

    r = redis.from_url(settings.REDIS_URL)
    key = f"pending-payment:{request.wompi_reference}"
    data = {
        "plan_id": request.plan_id,
        "member_id": str(member.id),
        "amount": str(request.amount),
        "wompi_reference": request.wompi_reference,
    }
    # TTL 24 hours — more than enough for a payment to complete
    r.setex(key, 86400, json.dumps(data))
    logger.info(f"Stored pending payment: {key} -> {data}")

    return {"status": "stored"}


@router.get("/pending-payment/{reference}")
def get_pending_payment(
    reference: str,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """
    Look up pending payment by Wompi reference.
    Requires internal API key for access.
    """
    from core.config import settings

    # Require internal API key
    internal_key = settings.SECRET_KEY
    if not x_api_key or x_api_key != internal_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

    import redis
    import json

    r = redis.from_url(settings.REDIS_URL)
    key = f"pending-payment:{reference}"
    data = r.get(key)

    if not data:
        return {"status": "not_found", "reference": reference}

    return {"status": "found", **json.loads(data)}
