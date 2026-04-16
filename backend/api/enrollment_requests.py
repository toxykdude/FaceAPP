"""
Enrollment request queue API — remote enrollment from Android tablet.

Endpoints:
  POST   /enrollment-requests                     ← Frontend creates request
  GET    /enrollment-requests/pending?device_id=   ← Android polls for work
  POST   /enrollment-requests/{id}/start           ← Android marks processing
  POST   /enrollment-requests/{id}/complete        ← Android sends result
  GET    /enrollment-requests/{id}                 ← Frontend checks status
  POST   /enrollment-requests/{id}/cancel          ← Frontend/Android cancels
"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from api.deps import get_db, get_current_user, require_staff
from models.member import Member
from models.enrollment_request import EnrollmentRequest
from models.user import User
from schemas.enrollment_request import (
    EnrollmentRequestCreate,
    EnrollmentRequestResponse,
    EnrollmentCompleteRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/enrollment-requests", tags=["Enrollment Requests"])


def _to_response(req: EnrollmentRequest, db: Session) -> EnrollmentRequestResponse:
    """Convert EnrollmentRequest model to response with member name."""
    member = db.query(Member).filter(Member.id == req.member_id).first()
    member_name = None
    if member:
        member_name = f"{member.first_name} {member.last_name or ''}".strip()

    return EnrollmentRequestResponse(
        id=req.id,
        member_id=req.member_id,
        member_name=member_name,
        device_id=req.device_id,
        status=req.status,
        quality_score=req.quality_score,
        result_message=req.result_message,
        created_at=req.created_at,
        started_at=req.started_at,
        completed_at=req.completed_at,
    )


# ---------------------------------------------------------------------------
# Frontend endpoints (require staff auth)
# ---------------------------------------------------------------------------

@router.post("", response_model=EnrollmentRequestResponse, status_code=status.HTTP_201_CREATED)
def create_enrollment_request(
    body: EnrollmentRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """
    Create a new enrollment request. The Android tablet will pick this up
    via the /pending endpoint and start the enrollment flow.

    Only one pending/processing request per member is allowed.
    """
    # Verify member exists
    member = db.query(Member).filter(Member.id == body.member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    # Check for existing pending/processing request for this member
    existing = db.query(EnrollmentRequest).filter(
        EnrollmentRequest.member_id == body.member_id,
        EnrollmentRequest.status.in_(["pending", "processing"]),
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Enrollment already in progress (request {existing.id})",
        )

    req = EnrollmentRequest(
        member_id=body.member_id,
        device_id=body.device_id,
        status="pending",
        created_by=current_user.id,
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    logger.info(f"Enrollment request created: {req.id} for member {member.first_name} (device={body.device_id})")
    return _to_response(req, db)


@router.get("/{request_id}", response_model=EnrollmentRequestResponse)
def get_enrollment_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get enrollment request status (for frontend polling)."""
    req = db.query(EnrollmentRequest).filter(EnrollmentRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    return _to_response(req, db)


@router.post("/{request_id}/cancel", response_model=EnrollmentRequestResponse)
def cancel_enrollment_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """Cancel a pending or processing enrollment request (from frontend)."""
    req = db.query(EnrollmentRequest).filter(EnrollmentRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    if req.status not in ("pending", "processing"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel request in status: {req.status}")

    req.status = "cancelled"
    req.completed_at = datetime.now(timezone.utc)
    req.result_message = "Cancelled by admin"
    db.commit()
    db.refresh(req)

    logger.info(f"Enrollment request cancelled: {request_id}")
    return _to_response(req, db)


# ---------------------------------------------------------------------------
# Android endpoints (no auth — internal kiosk device)
# ---------------------------------------------------------------------------

@router.get("/pending", response_model=list[EnrollmentRequestResponse])
def get_pending_requests(
    device_id: str = Query("kiosk-android", description="Device ID to check"),
    db: Session = Depends(get_db),
):
    """
    Get pending enrollment requests for a specific device.
    The Android tablet polls this endpoint every 2 seconds.
    """
    requests = db.query(EnrollmentRequest).filter(
        EnrollmentRequest.device_id == device_id,
        EnrollmentRequest.status == "pending",
    ).order_by(EnrollmentRequest.created_at.asc()).all()

    return [_to_response(r, db) for r in requests]


@router.post("/{request_id}/start", response_model=EnrollmentRequestResponse)
def start_enrollment_request(
    request_id: str,
    db: Session = Depends(get_db),
):
    """
    Android marks the request as processing (face capture in progress).
    """
    req = db.query(EnrollmentRequest).filter(EnrollmentRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    if req.status != "pending":
        raise HTTPException(status_code=400, detail=f"Request is not pending (status: {req.status})")

    req.status = "processing"
    req.started_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(req)

    logger.info(f"Enrollment request started: {request_id}")
    return _to_response(req, db)


@router.post("/{request_id}/complete", response_model=EnrollmentRequestResponse)
def complete_enrollment_request(
    request_id: str,
    body: EnrollmentCompleteRequest,
    db: Session = Depends(get_db),
):
    """
    Android completes the enrollment request with success/failure result.
    The actual enrollment (image upload to /enrollment/{member_id}/enroll)
    is done separately by the Android app before calling this endpoint.
    """
    req = db.query(EnrollmentRequest).filter(EnrollmentRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    if req.status not in ("processing", "pending"):
        raise HTTPException(status_code=400, detail=f"Request is not in progress (status: {req.status})")

    req.status = "complete" if body.success else "failed"
    req.quality_score = body.quality_score
    req.result_message = body.message or ("Enrollment successful" if body.success else "Enrollment failed")
    req.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(req)

    logger.info(f"Enrollment request completed: {request_id} (success={body.success}, quality={body.quality_score})")
    return _to_response(req, db)
