"""
Member Portal authentication endpoints (phone + WhatsApp PIN).
"""
import re
import random
import logging
import redis
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.deps import get_db
from core.config import settings
from core.security import create_access_token
from models.member import Member
from models.membership import Membership
from schemas.portal import MemberLoginRequest, MemberVerifyRequest, MemberPortalToken, MemberPortalResponse

router = APIRouter(prefix="/auth", tags=["Member Portal Auth"])

logger = logging.getLogger(__name__)

r = redis.from_url(settings.REDIS_URL, decode_responses=True)

PIN_TTL = 300
PIN_COOLDOWN = 60
MAX_FAILED_ATTEMPTS = 3
LOCKOUT_SECONDS = 600  # 10 minutes


def _check_lockout(phone: str) -> None:
    """Check if phone is locked out due to too many failed attempts."""
    lockout_key = f"member-lockout:{phone}"
    ttl = r.ttl(lockout_key)
    if ttl and ttl > 0:
        minutes_left = max(1, ttl // 60)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Por seguridad, espera {minutes_left} minutos antes de intentar de nuevo.",
        )


def _record_failed_attempt(phone: str) -> None:
    """Record a failed PIN attempt. Lock out after MAX_FAILED_ATTEMPTS."""
    attempts_key = f"member-failed:{phone}"
    attempts = r.incr(attempts_key)
    if attempts == 1:
        r.expire(attempts_key, LOCKOUT_SECONDS)
    if attempts >= MAX_FAILED_ATTEMPTS:
        r.setex(f"member-lockout:{phone}", LOCKOUT_SECONDS, "1")
        r.delete(attempts_key)


def _clear_failed_attempts(phone: str) -> None:
    """Clear failed attempts on successful verification."""
    r.delete(f"member-failed:{phone}")


def _normalize_phone(phone: str) -> str:
    return re.sub(r'\D', '', phone.strip())


def _generate_pin() -> str:
    return str(random.randint(100000, 999999))


def _resolve_member(db: Session, phone: str) -> Member:
    """
    Resolve a member by phone number.
    When multiple members share the same phone, prefer the one with
    an active membership (most likely the real member account).
    """
    members = db.query(Member).filter(Member.phone == phone, Member.status == "active").all()

    if not members:
        members = db.query(Member).filter(Member.phone == phone).all()

    if not members:
        return None

    if len(members) == 1:
        return members[0]

    today = date.today()
    for m in members:
        has_active = db.query(Membership).filter(
            Membership.member_id == m.id,
            Membership.status == "active",
            Membership.start_date <= today,
            Membership.end_date >= today,
        ).first()
        if has_active:
            return m

    members_with_history = []
    for m in members:
        count = db.query(Membership).filter(Membership.member_id == m.id).count()
        members_with_history.append((m, count))
    members_with_history.sort(key=lambda x: x[1], reverse=True)

    return members_with_history[0][0] if members_with_history else members[0]


def _ensure_country_code(phone: str) -> str:
    """Ensure phone has Colombia country code (57) for Evolution API."""
    if len(phone) == 10 and phone.startswith('3'):
        return f"57{phone}"
    return phone


async def _send_whatsapp_pin(phone: str, pin: str) -> None:
    """Send PIN via Evolution API WhatsApp message."""
    import httpx

    whatsapp_number = _ensure_country_code(phone)
    message = (
        f"🏋️ PowerHouse Gym\n\n"
        f"Tu código de verificación es: {pin}\n\n"
        f"Válido por 5 minutos."
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.EVOLUTION_API_URL}/message/sendText/{settings.EVOLUTION_INSTANCE_NAME}",
                json={"number": whatsapp_number, "text": message},
                headers={
                    "apikey": settings.EVOLUTION_API_KEY,
                    "Content-Type": "application/json",
                },
            )
            logger.info(f"WhatsApp PIN sent to {whatsapp_number}, status={resp.status_code}")
    except Exception as e:
        logger.error(f"Error sending WhatsApp PIN to {whatsapp_number}: {e}")


@router.post("/member-login")
async def member_login(
    request: MemberLoginRequest,
    db: Session = Depends(get_db),
):
    """
    Request a login PIN via WhatsApp.

    Validates phone number, generates 6-digit PIN, stores in Redis, sends via WhatsApp.
    """
    normalized_phone = _normalize_phone(request.phone)

    member = _resolve_member(db, normalized_phone)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No encontramos un miembro con ese número de celular. Contacta al gimnasio.",
        )

    # Check lockout before sending new PIN
    _check_lockout(normalized_phone)

    # Generate and store PIN
    pin = _generate_pin()
    r.setex(f"member-pin:{normalized_phone}", PIN_TTL, pin)

    # Send via WhatsApp (don't block on failure)
    await _send_whatsapp_pin(normalized_phone, pin)

    return {"message": "PIN enviado a tu WhatsApp", "expires_in": PIN_TTL}


@router.post("/member-verify", response_model=MemberPortalToken)
async def member_verify(
    request: MemberVerifyRequest,
    db: Session = Depends(get_db),
):
    """
    Verify phone + PIN and return JWT token.

    Validates the PIN stored in Redis, then issues a member JWT.
    """
    normalized_phone = _normalize_phone(request.phone)

    # Check lockout before verifying
    _check_lockout(normalized_phone)

    # Get stored PIN from Redis
    stored_pin = r.get(f"member-pin:{normalized_phone}")
    if not stored_pin or stored_pin != request.pin:
        _record_failed_attempt(normalized_phone)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Código incorrecto o expirado",
        )

    # PIN is valid — look up member
    member = _resolve_member(db, normalized_phone)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Miembro no encontrado",
        )

    # Delete PIN from Redis (single use)
    r.delete(f"member-pin:{normalized_phone}")

    # Clear any failed attempt counters
    _clear_failed_attempts(normalized_phone)

    # Create JWT with member type
    from datetime import timedelta
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(member.id), "type": "member"},
        expires_delta=access_token_expires,
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "member": member,
    }


@router.post("/member-resend")
async def member_resend(
    request: MemberLoginRequest,
    db: Session = Depends(get_db),
):
    """
    Resend a login PIN via WhatsApp (with 60s cooldown).

    Same flow as member-login but enforces a cooldown to prevent abuse.
    """
    normalized_phone = _normalize_phone(request.phone)

    # Check cooldown
    cooldown_key = f"member-pin-cooldown:{normalized_phone}"
    if r.exists(cooldown_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Espera 60 segundos antes de solicitar otro código",
        )

    # Look up member by phone
    member = _resolve_member(db, normalized_phone)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No encontramos un miembro con ese número de celular. Contacta al gimnasio.",
        )

    # Generate and store PIN
    pin = _generate_pin()
    r.setex(f"member-pin:{normalized_phone}", PIN_TTL, pin)

    # Set cooldown
    r.setex(cooldown_key, PIN_COOLDOWN, "1")

    # Send via WhatsApp (don't block on failure)
    await _send_whatsapp_pin(normalized_phone, pin)

    return {"message": "PIN enviado a tu WhatsApp", "expires_in": PIN_TTL}
