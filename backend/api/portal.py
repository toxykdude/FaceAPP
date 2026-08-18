"""
Member Portal endpoints — member self-service.
"""

import hashlib
import hmac
import json
import re
import uuid
from datetime import date, timedelta
from decimal import Decimal
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.deps import get_db, get_current_member, get_portal_session
from core.config import settings
from core.rate_limiter import limiter
from models.member import Member
from models.membership import Membership, MembershipPlan
from models.sale import SalesTransaction
from pydantic import ValidationError
from schemas.portal import (
    PortalMeResponse,
    PortalPlanResponse,
    PortalPendingPaymentRequest,
    PortalGuestPendingPaymentRequest,
    PortalRenewRequest,
    PortalRenewResponse,
    PortalWebhookRenewRequest,
    ActiveMembershipResponse,
    PaymentHistoryItem,
)
from services.canonical_phone import (
    canonicalize_phone,
    find_members_by_canonical_phone,
)
from services.cv_notify import notify_cv_invalidation

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
    active_membership = (
        db.query(Membership)
        .filter(
            Membership.member_id == str(member.id),
            Membership.status == "active",
            Membership.start_date <= today,
            Membership.end_date >= today,
        )
        .order_by(Membership.end_date.desc())
        .first()
    )

    active_membership_response = None
    if active_membership:
        # Get plan name
        plan_name = None
        if active_membership.plan_id:
            plan = (
                db.query(MembershipPlan)
                .filter(MembershipPlan.id == active_membership.plan_id)
                .first()
            )
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
async def portal_renew(
    request: PortalRenewRequest,
    member: Member = Depends(get_current_member),
    db: Session = Depends(get_db),
):
    """
    Confirm a Wompi-paid membership renewal.

    SECURITY: this route NEVER creates or activates a membership. Activation
    happens ONLY in the HMAC-verified /webhook-renew endpoint, after Wompi
    confirms the payment. Here we look up whether that webhook has already
    processed this wompi_reference for the authenticated member and return the
    resulting membership, or signal that payment has not been confirmed yet.

    `request.amount` is accepted for backward compatibility but IGNORED — the
    authoritative price is the plan's price (set server-side by the webhook).
    Previously this endpoint trusted the client amount + reference and created
    a membership directly, allowing free memberships (CWE-602/840).
    """
    # Verify plan exists and is active (validates plan_id early)
    plan = (
        db.query(MembershipPlan)
        .filter(
            MembershipPlan.id == request.plan_id,
            MembershipPlan.is_active == True,
        )
        .first()
    )

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan no encontrado o inactivo",
        )

    # Activation requires a VERIFIED payment. The webhook writes a
    # SalesTransaction whose notes carry the wompi_reference. If none exists
    # for THIS member + reference, payment has not been confirmed -> refuse.
    # (Scoped to member.id so a member cannot confirm another member's ref.)
    transaction = (
        db.query(SalesTransaction)
        .filter(
            SalesTransaction.member_id == str(member.id),
            SalesTransaction.notes.like(f"%{request.wompi_reference}%"),
        )
        .first()
    )
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Pago no confirmado aún",
        )

    # The verified webhook already created the membership; return it.
    membership = (
        db.query(Membership).filter(Membership.id == transaction.membership_id).first()
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Membresía no encontrada",
        )

    today = date.today()
    return PortalRenewResponse(
        membership=ActiveMembershipResponse(
            id=membership.id,
            type=membership.type,
            plan_name=plan.name,
            start_date=membership.start_date,
            end_date=membership.end_date,
            price=membership.price,
            status=membership.status,
            days_remaining=(membership.end_date - today).days,
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

        logging.getLogger(__name__).error(
            "WOMPI_INTEGRITY_SECRET not configured — webhook verification disabled"
        )
        return False

    expected = hmac.new(
        settings.WOMPI_INTEGRITY_SECRET.encode(),
        request_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature_header)


def _pending_key(reference: str) -> str:
    return f"pending-payment:{reference}"


def _load_pending_payment(reference: str):
    """Load the Redis pending record for a Wompi reference.

    Returns ``(redis_client, record_or_None)``. The record is server-authored
    (written by a JWT-authed or internal-keyed endpoint) and is the ONLY
    authoritative source of plan, member and amount for reconciliation.
    """
    import redis
    from core.config import settings

    client = redis.from_url(settings.REDIS_URL)
    raw = client.get(_pending_key(reference))
    return client, (json.loads(raw) if raw else None)


def _resolve_member_from_pending(db: Session, pending: dict):
    """Resolve which member a pending record provisions (design D5/D9 seam).

    The Redis ``member_id`` is authoritative — the webhook body's member_id
    is ignored (a signed relay forward must not choose the member). Returns
    None when the record carries no member_id: that is the guest-purchase
    branch, provisioned by the guest provisioning path (Unit 2) which plugs
    in exactly here.
    """
    member_id = pending.get("member_id")
    if not member_id:
        return None
    return db.query(Member).filter(Member.id == member_id).first()


def _already_processed(db: Session, reference: str):
    """Find an existing sale by Wompi reference (exact idempotency lookup)."""
    return (
        db.query(SalesTransaction)
        .filter(SalesTransaction.wompi_reference == reference)
        .first()
    )


def _begin_guest_provisioning(db: Session, redis_client, pending: dict, logger):
    """Guest branch (design D5): resolve or create the member a guest
    pending record provisions, under a Redis advisory lock.

    Dedup comes first — the canonical phone lookup is the SAME SQL the
    login path uses (services/canonical_phone.py): an existing member
    receives the purchase, an ambiguous legacy duplicate refuses (422,
    staff must merge), and only a genuinely new phone creates a Member
    (first token / remainder mapping, active, NO biometric consent).

    Concurrency: ``SET member-provision:{phone} NX EX 15`` serializes
    concurrent webhooks for one phone — the phone column is deliberately
    non-unique, so nothing else stops two racing webhooks from each
    creating a member. Returns ``(member, lock_key)``; the caller MUST
    release the lock once the provisioning transaction concludes (commit
    or rollback) — the EX 15 is only the crash safety net.
    """
    phone = pending.get("guest_phone") or ""
    if not re.fullmatch(r"57\d{10}", phone):
        logger.error(
            f"Webhook renew ALERT: guest pending record "
            f"{pending.get('wompi_reference')} carries invalid phone "
            f"{phone!r} — refusing to provision, key retained"
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Registro de invitado inválido",
        )

    lock_key = f"member-provision:{phone}"
    if not redis_client.set(lock_key, "1", nx=True, ex=15):
        logger.warning(
            f"Webhook renew: guest provisioning for {phone} already in "
            "progress (advisory lock held) — refusing concurrent attempt, "
            "pending key retained for replay"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Provisioning in progress, retry shortly",
        )

    try:
        candidates = find_members_by_canonical_phone(db, phone)
        if len(candidates) > 1:
            logger.error(
                f"Webhook renew ALERT: canonical phone {phone} matches "
                f"{len(candidates)} members (legacy duplicates) — refusing "
                "guest provisioning, staff must merge; no writes, key retained"
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="El teléfono coincide con varios miembros",
            )
        if candidates:
            logger.info(
                f"Webhook renew: guest {phone} attaches to existing member "
                f"{candidates[0].id}"
            )
            return candidates[0], lock_key

        tokens = (pending.get("guest_name") or "").strip().split()
        member = Member(
            first_name=tokens[0] if tokens else "Invitado",
            last_name=" ".join(tokens[1:]),
            email=pending.get("guest_email") or None,
            phone=phone,
            status="active",
            consent_given_at=None,  # a purchase is never biometric consent (D5)
            facial_data_enrolled=False,
        )

        # Email is unique on members but NOT part of the guest contract —
        # another household member may legitimately reuse an address. On a
        # collision, store NULL and log for staff reconciliation instead of
        # losing the paid provisioning.
        email_savepoint = db.begin_nested()
        db.add(member)
        try:
            db.flush()
        except IntegrityError:
            email_savepoint.rollback()
            logger.warning(
                f"Webhook renew: guest email {member.email} already in use "
                "— storing member with NULL email; staff should reconcile "
                "contact data"
            )
            member.email = None
            db.add(member)
            db.flush()

        logger.info(
            f"Webhook renew: created guest member for {phone} "
            f"({member.first_name!r} {member.last_name!r})"
        )
        return member, lock_key
    except Exception:
        # Provisioning failed before the commit phase — release the advisory
        # lock. The pending key stays retained, so a replay can retry once
        # the underlying problem clears.
        try:
            redis_client.delete(lock_key)
        except Exception:  # pragma: no cover — Redis availability edge
            logger.warning(
                f"Webhook renew: failed to release provisioning lock {lock_key}"
            )
        raise


@router.post("/webhook-renew")
async def portal_webhook_renew(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Renew membership from Wompi webhook — no JWT required.

    Called server-to-server by the Cloudflare Pages relay. Reconciliation
    order (design D9, spec payment-integrity "Webhook Re-Verification and
    Atomic Pending Consumption"):

    1. HMAC-SHA256 signature (401 before ANY lookup — forged webhooks
       change no state).
    2. Parse the v2 body: ``wompi_reference``, ``wompi_transaction_id`` and
       ``amount_in_cents`` are all required (422 otherwise).
    3. Load the Redis pending record by reference. Missing key + existing
       sale = replay → ``already_processed``; missing both = 404 + staff
       alert (covers TTL-expired legit payments — the relay alerts staff).
    4. Amount gates (D4): the pending record must equal the DB plan price
       (it is server-authored — any deviation is tampering or staleness)
       AND the Wompi ``amount_in_cents/100`` must be >= the plan price
       (overpayment accepted, underpayment never). Violation → 400 + alert,
       pending key retained.
    5. Resolve the member from the pending record (body member_id ignored).
       Guest records (v2, ``member_id`` null) resolve or CREATE their member
       under the ``member-provision:{phone}`` advisory lock (design D5):
       canonical-phone dedup, ambiguous legacy duplicates → 422, new phone
       → Member created with NO biometric consent, in the SAME commit as 6.
    6. Membership + SalesTransaction (+ ``wompi_reference``) in a single
       commit — the UNIQUE index makes a same-reference race abort the
       loser as ``already_processed``.
    7. Post-commit only: delete the Redis key strictly AFTER the commit
       (D1 — the key is never consumed unless provisioning committed),
       then notify CV (failure logged; the sale stays intact).
    """
    import logging

    logger = logging.getLogger(__name__)

    # 1. Verify Wompi signature — pre-lookup, no state change on failure.
    signature = request.headers.get("X-Signature", "")
    body = await request.body()

    if not verify_wompi_signature(body, signature):
        logger.warning("Webhook renew: invalid or missing Wompi signature")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )

    # 2. Parse the body as the v2 schema.
    try:
        body_data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON body",
        )

    try:
        request_data = PortalWebhookRenewRequest(**body_data)
    except ValidationError as exc:
        logger.warning(
            "Webhook renew: rejected malformed body (missing or invalid "
            f"required fields): {exc.errors()}"
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid webhook payload",
        )

    reference = request_data.wompi_reference

    # 3. Redis pending load (authoritative) with DB idempotency fallback.
    r, pending = _load_pending_payment(reference)
    if pending is None:
        existing_tx = _already_processed(db, reference)
        if existing_tx:
            logger.info(
                f"Webhook renew: reference {reference} already processed, skipping"
            )
            return {
                "status": "already_processed",
                "membership_id": (
                    str(existing_tx.membership_id)
                    if existing_tx.membership_id
                    else None
                ),
            }
        logger.error(
            f"Webhook renew ALERT: no pending record and no prior sale for "
            f"reference {reference} — refusing to provision (TTL expiry or "
            "unverified request; staff should reconcile this payment)"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Referencia de pago no encontrada",
        )

    # 4. Amount gates (D4) — plan resolved from the pending record.
    plan = (
        db.query(MembershipPlan)
        .filter(
            MembershipPlan.id == pending.get("plan_id"),
            MembershipPlan.is_active == True,
        )
        .first()
    )
    if not plan:
        logger.error(
            f"Webhook renew ALERT: pending record {reference} references "
            f"unknown or inactive plan {pending.get('plan_id')} — refusing to "
            "provision, key retained"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan no encontrado o inactivo",
        )

    pending_amount = Decimal(str(pending.get("amount", "")))
    wompi_amount = Decimal(request_data.amount_in_cents) / Decimal(100)
    if pending_amount != plan.price or wompi_amount < plan.price:
        logger.error(
            f"Webhook renew ALERT: amount mismatch for reference {reference} "
            f"(pending={pending_amount}, wompi={wompi_amount}, "
            f"plan_price={plan.price}) — no provisioning, pending key retained"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Monto del pago no coincide con el plan",
        )

    # 5. Resolve the member — Redis pending record authoritative (D9).
    # Guest records (member_id null, v2) resolve or create their member
    # here under the provisioning advisory lock (D5); member-bound records
    # whose member vanished stay a 404 (never silently re-created).
    member = _resolve_member_from_pending(db, pending)
    provision_lock_key = None
    if member is None and not pending.get("member_id"):
        member, provision_lock_key = _begin_guest_provisioning(db, r, pending, logger)
    if member is None:
        logger.error(
            f"Webhook renew ALERT: pending record {reference} carries an "
            "unresolvable member_id (member deleted?) — refusing to "
            "provision, key retained"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Miembro no encontrado",
        )

    today = date.today()

    # Check for existing active membership — extend from current end_date
    active_membership = (
        db.query(Membership)
        .filter(
            Membership.member_id == str(member.id),
            Membership.status == "active",
            Membership.start_date <= today,
            Membership.end_date >= today,
        )
        .order_by(Membership.end_date.desc())
        .first()
    )

    start_date = today
    if active_membership and active_membership.end_date >= today:
        start_date = active_membership.end_date + timedelta(days=1)

    end_date = start_date + timedelta(days=plan.duration_days)

    # 6. Membership + Sale (+ wompi_reference idempotency key) single commit
    # — for guests this is the SAME commit as the Member insert, so all
    # three records are atomic (spec: Atomic Provisioning on Approved
    # Payment). A SAVEPOINT scopes the attempt: when the UNIQUE index
    # aborts a same-reference race loser, only the loser's rows are
    # discarded — never anything committed by another transaction.
    nested = db.begin_nested()
    try:
        new_membership = Membership(
            member_id=str(member.id),
            plan_id=plan.id,
            type=plan.name,
            start_date=start_date,
            end_date=end_date,
            price=plan.price,  # server-derived; never trust the webhook body amount
            status="active",
        )
        db.add(new_membership)
        db.flush()

        invoice_number = (
            f"WOM-{today.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        )

        transaction = SalesTransaction(
            member_id=str(member.id),
            membership_id=new_membership.id,
            amount=plan.price,  # server-derived; never trust the webhook body amount
            payment_method="card",
            invoice_number=invoice_number,
            notes=(
                f"Wompi ref: {request_data.wompi_reference} | "
                f"Wompi tx: {request_data.wompi_transaction_id}"
            ),
            wompi_reference=request_data.wompi_reference,
        )
        db.add(transaction)

        try:
            db.flush()
            db.commit()
        except IntegrityError:
            # Same-reference race: the UNIQUE index aborted this transaction —
            # the winner's commit is the authoritative provisioning.
            nested.rollback()
            winner = _already_processed(db, reference)
            logger.info(
                f"Webhook renew: unique wompi_reference race on {reference}; "
                "loser aborted, winner's provisioning stands"
            )
            return {
                "status": "already_processed",
                "membership_id": (
                    str(winner.membership_id)
                    if winner and winner.membership_id
                    else None
                ),
            }
    finally:
        if provision_lock_key:
            # The advisory lock only spans resolution → commit of the member
            # row; once the transaction concludes (either way) it must go so
            # the next webhook for this phone can proceed.
            try:
                r.delete(provision_lock_key)
            except Exception as exc:  # pragma: no cover — Redis edge
                logger.warning(
                    "Webhook renew: failed to release provisioning lock "
                    f"{provision_lock_key} ({exc}); EX TTL will expire it"
                )

    db.refresh(new_membership)
    db.refresh(transaction)

    # 7. Post-commit only — never on a failed/rolled-back write. The Redis
    # key is deleted strictly AFTER the commit: if this delete fails the DB
    # idempotency still guards replays (already_processed), so a Redis hiccup
    # never loses money but also never double-provisions.
    try:
        r.delete(_pending_key(reference))
    except Exception as exc:  # pragma: no cover — Redis availability edge
        logger.warning(
            f"Webhook renew: failed to delete pending key for {reference} "
            f"({exc}); DB idempotency still guards replays"
        )

    try:
        await notify_cv_invalidation(str(member.id))
    except Exception as exc:
        logger.error(
            f"Webhook renew: CV invalidation failed for member {member.id} "
            f"after committed provisioning ({exc}) — sale stays intact"
        )

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
    request: PortalPendingPaymentRequest,
    member: Member = Depends(get_current_member),
    db: Session = Depends(get_db),
):
    """
    Store pending payment info in Redis BEFORE opening Wompi widget.
    The webhook later reads this to activate membership.

    The stored amount is the plan's server-side price — never the client's
    `request.amount` — so a member cannot pin a lower amount for a plan.
    """
    import redis
    import json
    from core.config import settings
    import logging

    logger = logging.getLogger(__name__)

    # Resolve the authoritative price from the plan (server-side).
    plan = (
        db.query(MembershipPlan)
        .filter(
            MembershipPlan.id == request.plan_id,
            MembershipPlan.is_active == True,
        )
        .first()
    )
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan no encontrado o inactivo",
        )

    r = redis.from_url(settings.REDIS_URL)
    key = f"pending-payment:{request.wompi_reference}"
    data = {
        "plan_id": str(plan.id),
        "member_id": str(member.id),
        "amount": str(plan.price),  # server-derived, never the client amount
        "wompi_reference": request.wompi_reference,
    }
    # TTL 24 hours — more than enough for a payment to complete
    r.setex(key, 86400, json.dumps(data))
    logger.info(f"Stored pending payment: {key} -> {data}")

    return {"status": "stored"}


@router.post("/pending-payment/guest")
@limiter.limit(settings.GUEST_CHECKOUT_RATE_LIMIT)
def portal_guest_pending_payment(
    request: Request,
    body: PortalGuestPendingPaymentRequest,
    db: Session = Depends(get_db),
):
    """
    Store the GUEST pending payment record in Redis (no JWT — design D10).

    Guests have no portal token, so identity travels instead of a member
    binding: name, email and a phone that MUST normalize to canonical
    ``57 + 10 digits`` (anything else is 422 with NO record stored — a
    non-normalizable phone could never be deduplicated at provisioning
    time). The reference is validated against the Pages signature format
    before Redis is touched, the plan price is resolved from the database
    (active plans only), and the record carries ``member_id: null`` — the
    webhook's guest branch decides attach-vs-create when Wompi approves.
    """
    import logging

    logger = logging.getLogger(__name__)

    # Canonical phone: exactly 57 + 10 digits, or refuse without storing.
    canonical = canonicalize_phone(body.guest_phone)
    if not re.fullmatch(r"57\d{10}", canonical):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El teléfono debe ser un móvil colombiano (57 + 10 dígitos)",
        )

    # Plan price is server-side only (active plans — same contract as the
    # JWT member path).
    plan = (
        db.query(MembershipPlan)
        .filter(
            MembershipPlan.id == body.plan_id,
            MembershipPlan.is_active == True,
        )
        .first()
    )
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan no encontrado o inactivo",
        )

    import redis

    r = redis.from_url(settings.REDIS_URL)
    key = _pending_key(body.wompi_reference)
    data = {
        "v": 2,
        "plan_id": str(plan.id),
        "member_id": None,  # identity, not a member — webhook resolves later
        "guest_name": body.guest_name,
        "guest_phone": canonical,
        "guest_email": str(body.guest_email),
        "amount": str(plan.price),  # server-derived; no client amount exists
        "wompi_reference": body.wompi_reference,
    }
    # TTL 24 hours — the guest must complete payment within the same window
    # as members (spec: TTL not exceeding 24 hours).
    r.setex(key, 86400, json.dumps(data))
    logger.info(
        f"Stored guest pending payment: {key} (phone {canonical}, " f"plan {plan.name})"
    )

    return {"status": "stored"}


@router.get("/pending-payment/{reference}")
def get_pending_payment(
    reference: str,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """
    Look up pending payment by Wompi reference (relay-only, WS-1).

    Authenticates with the dedicated PORTAL_INTERNAL_API_KEY shared between
    the Pages relay and the backend. Fail closed: unset/empty key denies
    every read. The global SECRET_KEY is deliberately NOT accepted (a
    SECRET_KEY leak must not expose payment references), and denials are
    uniform 401s raised BEFORE any Redis access — a caller cannot probe
    whether a reference exists.
    """
    import redis
    import json

    from core.config import settings

    internal_key = settings.PORTAL_INTERNAL_API_KEY
    if (
        not internal_key
        or not x_api_key
        or not hmac.compare_digest(
            x_api_key.encode("utf-8"), internal_key.encode("utf-8")
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

    r = redis.from_url(settings.REDIS_URL)
    key = f"pending-payment:{reference}"
    data = r.get(key)

    if not data:
        return {"status": "not_found", "reference": reference}

    return {"status": "found", **json.loads(data)}
