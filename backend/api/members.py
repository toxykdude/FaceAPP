"""
Members API endpoints.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from datetime import datetime, timezone

import io

from api.deps import get_db, require_staff
from core.config import settings
from core.path_validation import validate_path
from models.user import User
from models.member import Member, MemberStatus
from models.event import AccessEvent
from models.biometric import BiometricTemplate
from schemas.member import (
    MemberCreate,
    MemberUpdate,
    MemberResponse,
    MemberListResponse,
    BiometricStatusResponse,
)
from services.cv_notify import notify_cv_invalidation

router = APIRouter(prefix="/members", tags=["Members"])

_MEMBER_EMAIL_CONSTRAINTS = {"members_email_key", "ix_members_email"}


def _member_integrity_conflict(error: IntegrityError) -> HTTPException:
    constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
    if constraint in _MEMBER_EMAIL_CONSTRAINTS:
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Member conflicts with existing data",
    )


@router.get("", response_model=MemberListResponse)
def list_members(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[MemberStatus] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """
    List all members with pagination and filtering.

    - **skip**: Number of records to skip (default: 0)
    - **limit**: Maximum number of records to return (default: 100)
    - **status**: Filter by member status
    - **search**: Search by name or email
    """
    query = db.query(Member)

    # Filter by status
    if status:
        query = query.filter(Member.status == status.value)

    # Search by name, email, or id_number
    # Multi-word: ALL words must match somewhere (AND between words, OR between fields)
    if search:
        from sqlalchemy import func, or_, and_

        words = search.strip().split()

        # Build per-word conditions: each word must match at least one field
        word_filters = []
        for word in words:
            word_filters.append(
                or_(
                    Member.first_name.ilike(f"%{word}%"),
                    Member.last_name.ilike(f"%{word}%"),
                    Member.email.ilike(f"%{word}%"),
                    Member.id_number.ilike(f"%{word}%"),
                    func.concat(Member.first_name, " ", Member.last_name).ilike(
                        f"%{word}%"
                    ),
                )
            )

        # All words must match (AND), each word can match any field (OR)
        query = query.filter(and_(*word_filters))

    # Get total count
    total = query.count()

    # Get paginated results
    members = query.order_by(Member.created_at.desc()).offset(skip).limit(limit).all()

    # Enrich members with active membership info
    from models.membership import Membership

    today = datetime.now(timezone.utc).date()

    member_data = []
    for m in members:
        active_mem = (
            db.query(Membership)
            .filter(
                Membership.member_id == m.id,
                Membership.status == "active",
                Membership.end_date >= today,
            )
            .order_by(Membership.end_date.desc())
            .first()
        )

        expired_mem = None
        if not active_mem:
            expired_mem = (
                db.query(Membership)
                .filter(
                    Membership.member_id == m.id,
                )
                .order_by(Membership.end_date.desc())
                .first()
            )

        from models.membership import MembershipPlan

        plan_name = None
        if active_mem and active_mem.plan_id:
            plan = (
                db.query(MembershipPlan)
                .filter(MembershipPlan.id == active_mem.plan_id)
                .first()
            )
            plan_name = plan.name if plan else None

        m_dict = {
            "id": str(m.id),
            "first_name": m.first_name,
            "last_name": m.last_name,
            "email": m.email,
            "phone": m.phone,
            "status": m.status,
            "facial_data_enrolled": m.facial_data_enrolled,
            "consent_given_at": m.consent_given_at,
            "id_number": m.id_number,
            "created_at": m.created_at,
            "updated_at": m.updated_at,
            "last_seen": (
                m.last_seen.replace(tzinfo=timezone.utc).isoformat()
                if m.last_seen
                else None
            ),
            "membership_status": (
                "active" if active_mem else ("expired" if expired_mem else None)
            ),
            "membership_end_date": (
                str(active_mem.end_date)
                if active_mem
                else (
                    str(expired_mem.end_date)
                    if expired_mem and expired_mem.end_date
                    else None
                )
            ),
            "membership_plan_name": plan_name
            or (active_mem.type if active_mem else None),
        }
        member_data.append(m_dict)

    return {"total": total, "members": member_data}


@router.post("", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
def create_member(
    member: MemberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """
    Create a new member.

    Requires staff or admin role.
    """
    # Check if email already exists
    if member.email:
        existing = db.query(Member).filter(Member.email == member.email).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

    # Create member
    db_member = Member(
        first_name=member.first_name,
        last_name=member.last_name,
        email=member.email,
        phone=member.phone,
        id_number=member.id_number,
        status=MemberStatus.ACTIVE.value,
        consent_given_at=datetime.now(timezone.utc) if member.consent_given else None,
    )

    try:
        db.add(db_member)
        db.flush()  # populate db_member.id for the audit row
        # Audit (atomic with the member write — log_action flushes; the commit
        # below persists both, so a create never completes without a durable audit).
        from core.audit import log_action

        log_action(
            db,
            action="create",
            resource_type="member",
            resource_id=str(db_member.id),
            user_id=str(current_user.id),
            username=current_user.username,
            details={"name": f"{db_member.first_name} {db_member.last_name}"},
        )
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise _member_integrity_conflict(error) from None
    db.refresh(db_member)

    return db_member


@router.get("/{member_id}/photo")
def get_member_photo(
    member_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """Get member photo from latest access event snapshot or generated initials avatar."""
    import os

    # 1. Check dedicated member photo first
    photo_path = f"/var/lib/powerhouse/member-photos/{member_id}.jpg"
    if os.path.exists(photo_path):
        try:
            safe_path = validate_path(photo_path)
            return FileResponse(safe_path, media_type="image/jpeg")
        except ValueError:
            pass  # Path traversal attempt — skip

    # 2. Try to find latest granted event with snapshot
    event = (
        db.query(AccessEvent)
        .filter(
            AccessEvent.member_id == member_id,
            AccessEvent.access_granted == True,
            AccessEvent.frame_snapshot_path.isnot(None),
        )
        .order_by(AccessEvent.timestamp.desc())
        .first()
    )

    if (
        event
        and event.frame_snapshot_path
        and os.path.exists(event.frame_snapshot_path)
    ):
        try:
            safe_path = validate_path(event.frame_snapshot_path)
            return FileResponse(safe_path, media_type="image/jpeg")
        except ValueError:
            pass  # Path traversal attempt — skip

    # Try any event with snapshot (denied events always have snapshots)
    event = (
        db.query(AccessEvent)
        .filter(
            AccessEvent.member_id == member_id,
            AccessEvent.frame_snapshot_path.isnot(None),
        )
        .order_by(AccessEvent.timestamp.desc())
        .first()
    )

    if (
        event
        and event.frame_snapshot_path
        and os.path.exists(event.frame_snapshot_path)
    ):
        try:
            safe_path = validate_path(event.frame_snapshot_path)
            return FileResponse(safe_path, media_type="image/jpeg")
        except ValueError:
            pass  # Path traversal attempt — skip

    # Fallback: generate initials avatar
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    try:
        from PIL import Image, ImageDraw, ImageFont

        initials = (member.first_name[0] if member.first_name else "?").upper()
        initials += (member.last_name[0] if member.last_name else "").upper()

        img = Image.new("RGB", (200, 200), color=(102, 126, 234))
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 80
            )
        except Exception:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), initials, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        draw.text(
            ((200 - text_w) / 2, (200 - text_h) / 2 - 10),
            initials,
            fill="white",
            font=font,
        )

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        return Response(content=buf.read(), media_type="image/png")
    except ImportError:
        raise HTTPException(status_code=404, detail="No photo available")


@router.get("/{member_id}", response_model=MemberResponse)
def get_member(
    member_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """
    Get member by ID.
    """
    member = db.query(Member).filter(Member.id == member_id).first()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Member not found"
        )

    return member


@router.put("/{member_id}", response_model=MemberResponse)
async def update_member(
    member_id: str,
    member_update: MemberUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """
    Update member information.
    """
    member = db.query(Member).filter(Member.id == member_id).first()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Member not found"
        )

    # Check email uniqueness if updating
    if member_update.email and member_update.email != member.email:
        existing = db.query(Member).filter(Member.email == member_update.email).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

    # Update fields
    update_data = member_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "status" and value:
            setattr(member, field, value.value)
        else:
            setattr(member, field, value)

    member.updated_at = datetime.now(timezone.utc)

    try:
        db.flush()
        # Audit remains atomic with the member write; commit persists both.
        from core.audit import log_action

        log_action(
            db,
            action="update",
            resource_type="member",
            resource_id=str(member.id),
            user_id=str(current_user.id),
            username=current_user.username,
            details={"updated_fields": list(update_data.keys())},
        )
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise _member_integrity_conflict(error) from None
    db.refresh(member)

    # Invalidate CV cache if member status changed
    if "status" in update_data:
        await notify_cv_invalidation(str(member.id))

    return member


@router.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_member(
    member_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """
    Delete a member.

    This will also delete associated biometric data (CASCADE).
    """
    member = db.query(Member).filter(Member.id == member_id).first()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Member not found"
        )

    # Delete member (biometric template will be deleted via CASCADE)
    db.delete(member)
    # Audit (atomic with the deletion — log_action flushes; the commit below
    # persists both, so a delete never completes without a durable audit).
    from core.audit import log_action

    log_action(
        db,
        action="delete",
        resource_type="member",
        resource_id=str(member_id),
        user_id=str(current_user.id),
        username=current_user.username,
    )
    db.commit()

    await notify_cv_invalidation(str(member_id))

    return None


@router.get("/{member_id}/biometric-status", response_model=BiometricStatusResponse)
def get_biometric_status(
    member_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """
    Get biometric enrollment status for a member.
    """
    member = db.query(Member).filter(Member.id == member_id).first()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Member not found"
        )

    # Get biometric template if exists
    template = (
        db.query(BiometricTemplate)
        .filter(BiometricTemplate.member_id == member_id)
        .first()
    )

    return {
        "member_id": str(member.id),
        "enrolled": member.facial_data_enrolled,
        "quality_score": template.quality_score if template else None,
        "enrolled_at": template.enrolled_at if template else None,
    }
