"""
Member Portal authentication endpoints (phone + WhatsApp PIN).
"""

import hmac
import json
import logging
import random
import re
import redis
from typing import NoReturn
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import and_, case, func
from sqlalchemy.orm import Session

from api.deps import get_db
from core.config import settings
from core.rate_limiter import limiter
from core.security import create_access_token
from models.member import Member
from schemas.portal import (
    MemberLoginRequest,
    MemberVerifyRequest,
    MemberPortalToken,
    MemberPortalResponse,
)

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


def _canonicalize_phone(phone: str) -> str:
    digits = re.sub(r"[^0-9]", "", phone)
    if len(digits) == 10 and digits.startswith("3"):
        return f"57{digits}"
    return digits


def _generate_pin() -> str:
    return str(random.randint(100000, 999999))


def _resolve_member(db: Session, destination: str) -> Member | None:
    """Return a member only for one unambiguous WhatsApp destination."""
    if not destination:
        return None

    digits = func.regexp_replace(Member.phone, "[^0-9]", "", "g")
    stored_destination = case(
        (
            and_(func.length(digits) == 10, digits.like("3%")),
            func.concat("57", digits),
        ),
        else_=digits,
    )
    candidates = (
        db.query(Member).filter(stored_destination == destination).limit(2).all()
    )
    return candidates[0] if len(candidates) == 1 else None


def _ensure_country_code(phone: str) -> str:
    """Ensure phone has Colombia country code (57) for Evolution API."""
    if len(phone) == 10 and phone.startswith("3"):
        return f"57{phone}"
    return phone


def _encode_challenge(pin: str, member: Member) -> str:
    return json.dumps({"member_id": str(member.id), "pin": pin}, separators=(",", ":"))


def _decode_challenge(value: str | None) -> tuple[str, str] | None:
    try:
        challenge = json.loads(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    if not isinstance(challenge, dict) or set(challenge) != {"member_id", "pin"}:
        return None
    member_id, pin = challenge["member_id"], challenge["pin"]
    if not isinstance(member_id, str) or not isinstance(pin, str):
        return None
    if not re.fullmatch(r"\d{6}", pin):
        return None
    try:
        return pin, str(UUID(member_id))
    except ValueError:
        return None


def _deny_pin(destination: str, *, discard_challenge: bool = False) -> NoReturn:
    if discard_challenge:
        r.delete(f"member-pin:{destination}")
    _record_failed_attempt(destination)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Código incorrecto o expirado",
    )


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
            logger.info("WhatsApp PIN delivery completed, status=%s", resp.status_code)
    except Exception:
        logger.error("WhatsApp PIN delivery failed")


@router.post("/member-login")
@limiter.limit(settings.MEMBER_AUTH_RATE_LIMIT)
async def member_login(
    request: Request,
    body: MemberLoginRequest,
    db: Session = Depends(get_db),
):
    """
    Request a login PIN via WhatsApp.

    Validates phone number, generates 6-digit PIN, stores in Redis, sends via WhatsApp.
    """
    destination = _canonicalize_phone(body.phone)

    # Look up the member (unknown phones run the exact same flow below,
    # minus the WhatsApp send — see the send comment for why).
    member = _resolve_member(db, destination)

    # Check lockout before sending new PIN
    _check_lockout(destination)

    # Check 60s cooldown
    cooldown_key = f"member-pin-cooldown:{destination}"
    if r.exists(cooldown_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Espera 60 segundos antes de solicitar otro código",
        )

    # Set cooldown
    r.setex(cooldown_key, PIN_COOLDOWN, "1")

    # Send via WhatsApp (don't block on failure). Unknown phones get the SAME
    # 200 response but no message is sent: sending WhatsApp messages to
    # arbitrary attacker-supplied numbers is its own abuse vector, and the
    # identical response shape prevents phone-number enumeration.
    if member:
        pin = _generate_pin()
        r.setex(f"member-pin:{destination}", PIN_TTL, _encode_challenge(pin, member))
        await _send_whatsapp_pin(destination, pin)

    return {"message": "PIN enviado a tu WhatsApp", "expires_in": PIN_TTL}


@router.post("/member-verify", response_model=MemberPortalToken)
@limiter.limit(settings.MEMBER_AUTH_RATE_LIMIT)
async def member_verify(
    request: Request,
    body: MemberVerifyRequest,
    db: Session = Depends(get_db),
):
    """
    Verify phone + PIN and return JWT token.

    Validates the PIN stored in Redis, then issues a member JWT.
    """
    destination = _canonicalize_phone(body.phone)

    # Check lockout before verifying
    _check_lockout(destination)

    # Get stored PIN from Redis
    stored_challenge = r.get(f"member-pin:{destination}")
    challenge = _decode_challenge(stored_challenge)
    if not challenge:
        _deny_pin(destination, discard_challenge=stored_challenge is not None)
    stored_pin, bound_member_id = challenge
    if not hmac.compare_digest(stored_pin, body.pin):
        _deny_pin(destination)

    # PIN is valid — look up member. A valid PIN that resolves to no member
    # must be indistinguishable from a wrong PIN (WS-9, CWE-203): in practice
    # the PIN was never sent to unknown phones, but the response shape must
    # not differ from the wrong-PIN case.
    member = _resolve_member(db, destination)
    if not member or str(member.id) != bound_member_id:
        _deny_pin(destination, discard_challenge=True)

    # Delete PIN from Redis (single use)
    r.delete(f"member-pin:{destination}")

    # Clear any failed attempt counters
    _clear_failed_attempts(destination)

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
@limiter.limit(settings.MEMBER_AUTH_RATE_LIMIT)
async def member_resend(
    request: Request,
    body: MemberLoginRequest,
    db: Session = Depends(get_db),
):
    """
    Resend a login PIN via WhatsApp (with 60s cooldown).

    Same flow as member-login but enforces a cooldown to prevent abuse.
    """
    destination = _canonicalize_phone(body.phone)

    # Check cooldown
    cooldown_key = f"member-pin-cooldown:{destination}"
    if r.exists(cooldown_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Espera 60 segundos antes de solicitar otro código",
        )

    # Look up member by phone (unknown phones run the same flow, minus the
    # WhatsApp send — see member_login for the enumeration/abuse rationale)
    member = _resolve_member(db, destination)

    # Set cooldown
    r.setex(cooldown_key, PIN_COOLDOWN, "1")

    # Send via WhatsApp (don't block on failure) — only for known members
    if member:
        pin = _generate_pin()
        r.setex(f"member-pin:{destination}", PIN_TTL, _encode_challenge(pin, member))
        await _send_whatsapp_pin(destination, pin)

    return {"message": "PIN enviado a tu WhatsApp", "expires_in": PIN_TTL}
