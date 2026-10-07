"""
WiFi captive-portal internal + admin endpoints.

Consumed by the radius_service (X-Internal-Secret, same fail-closed guard as
the /cv/* internal API) for authorization decisions and RADIUS accounting,
and by admin/staff clients for the session listing.

The decision logic lives in services/wifi_auth.py; the accounting upsert
lives in services/wifi_accounting.py. This layer only wires HTTP.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.cv_internal import verify_internal_secret
from api.deps import get_db, require_staff
from models.user import User
from models.wifi_session import WifiSession
from schemas.wifi import (
    WiFiAccountingRequest,
    WiFiAccountingResponse,
    WiFiAuthorizeRequest,
    WiFiAuthorizeResponse,
    WiFiSessionListResponse,
    WiFiSessionResponse,
)
from services.wifi_accounting import record_wifi_accounting
from services.wifi_auth import evaluate_wifi_authorization

router = APIRouter(prefix="/wifi", tags=["WiFi Captive Portal"])


@router.post("/authorize", response_model=WiFiAuthorizeResponse)
def authorize(
    payload: WiFiAuthorizeRequest,
    db: Session = Depends(get_db),
    _: str = Depends(verify_internal_secret),
):
    """
    Decide whether a document number (cédula) may use the member WiFi.

    Rules mirror the kiosk (see services/wifi_auth.py): active member,
    active membership inside its date window (configured timezone), and at
    least partial payment. On a grant the response carries the RADIUS
    attributes pfSense should enforce (session/idle timeouts).
    """
    decision = evaluate_wifi_authorization(db, payload.document)
    return WiFiAuthorizeResponse(**decision)


@router.post("/accounting", response_model=WiFiAccountingResponse)
def accounting(
    payload: WiFiAccountingRequest,
    db: Session = Depends(get_db),
    _: str = Depends(verify_internal_secret),
):
    """
    Persist a RADIUS accounting event (start / interim / stop) as a
    wifi_sessions row, idempotently keyed on (nas_ip, acct_session_id).
    """
    session_id, member_id = record_wifi_accounting(db, payload)
    # get_db does not auto-commit (house style: write endpoints commit).
    db.commit()
    return WiFiAccountingResponse(
        recorded=True, session_id=session_id, member_id=member_id
    )


@router.get("/sessions", response_model=WiFiSessionListResponse)
def list_sessions(
    active_only: bool = Query(False, description="Only open (not ended) sessions"),
    member_id: Optional[UUID] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """
    List WiFi captive-portal sessions (admin/staff).

    Ordered newest-first. `active_only` filters to sessions without an
    `ended_at` — the "who is on the WiFi right now" view.
    """
    _ = current_user  # require_staff already enforced role; silence linters

    query = db.query(WifiSession)
    if active_only:
        query = query.filter(WifiSession.ended_at.is_(None))
    if member_id is not None:
        query = query.filter(WifiSession.member_id == member_id)

    total = query.count()
    sessions = (
        query.order_by(WifiSession.started_at.desc()).offset(offset).limit(limit).all()
    )

    return WiFiSessionListResponse(
        total=total,
        sessions=[WiFiSessionResponse.model_validate(s) for s in sessions],
    )
