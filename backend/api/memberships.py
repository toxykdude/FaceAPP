"""
Memberships API endpoints.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, date, timedelta, timezone

from api.deps import get_db, require_staff, require_admin
from models.user import User
from models.member import Member
from models.membership import Membership, MembershipStatus, MembershipPlan
from schemas.membership import (
    MembershipCreate,
    MembershipUpdate,
    MembershipResponse,
    MembershipListResponse,
)
from services.cv_notify import notify_cv_invalidation

router = APIRouter(prefix="/memberships", tags=["Memberships"])


@router.get("", response_model=MembershipListResponse)
def list_memberships(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    member_id: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """
    List all memberships with pagination and filtering.

    - **skip**: Number of records to skip
    - **limit**: Maximum number of records to return
    - **member_id**: Filter by member ID
    - **status**: Filter by membership status (active, expired, suspended)
    """
    query = db.query(Membership)

    # Filter by member
    if member_id:
        query = query.filter(Membership.member_id == member_id)

    # Filter by status
    if status:
        query = query.filter(Membership.status == status)

    # Get total count
    total = query.count()

    # Get paginated results
    memberships = (
        query.order_by(Membership.created_at.desc())
        .offset(skip)
        .limit(limit)
        .options(
            joinedload(Membership.member),
            joinedload(Membership.plan),
        )
        .all()
    )

    # Enrich with member and plan names
    result = []
    for m in memberships:
        member = m.member
        plan = m.plan if m.plan_id else None

        m_dict = {
            "id": str(m.id),
            "member_id": str(m.member_id),
            "plan_id": str(m.plan_id) if m.plan_id else None,
            "type": m.type,
            "start_date": m.start_date,
            "end_date": m.end_date,
            "price": m.price,
            "status": m.status,
            "access_rules": m.access_rules,
            "created_at": m.created_at,
            "updated_at": m.updated_at,
            "member_name": (
                f"{member.first_name} {member.last_name}" if member else "Unknown"
            ),
            "member_id_number": member.id_number if member else None,
            "plan_name": plan.name if plan else None,
        }
        result.append(m_dict)

    return {"total": total, "memberships": result}


@router.post("", response_model=MembershipResponse, status_code=status.HTTP_201_CREATED)
def create_membership(
    membership: MembershipCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """
    Create a new membership for a member.

    Requires staff or admin role.
    """
    # Verify member exists
    member = db.query(Member).filter(Member.id == membership.member_id).first()
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Member not found"
        )

    # Validate dates
    if membership.end_date <= membership.start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End date must be after start date",
        )

    # Create membership
    db_membership = Membership(
        member_id=membership.member_id,
        plan_id=membership.plan_id,
        type=membership.type,
        start_date=membership.start_date,
        end_date=membership.end_date,
        price=membership.price,
        status=MembershipStatus.ACTIVE.value,
        access_rules=(
            membership.access_rules.model_dump() if membership.access_rules else {}
        ),
    )

    db.add(db_membership)
    db.commit()
    db.refresh(db_membership)

    return db_membership


@router.get("/{membership_id}", response_model=MembershipResponse)
def get_membership(
    membership_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """
    Get membership by ID.
    """
    membership = db.query(Membership).filter(Membership.id == membership_id).first()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found"
        )

    return membership


@router.put("/{membership_id}", response_model=MembershipResponse)
def update_membership(
    membership_id: str,
    membership_update: MembershipUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """
    Update membership information.
    """
    membership = db.query(Membership).filter(Membership.id == membership_id).first()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found"
        )

    # Update fields
    update_data = membership_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "access_rules" and value:
            setattr(membership, field, value.model_dump())
        else:
            setattr(membership, field, value)

    membership.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(membership)

    return membership


@router.delete("/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_membership(
    membership_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Delete a membership. Admin only.
    """
    membership = db.query(Membership).filter(Membership.id == membership_id).first()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found"
        )

    db.delete(membership)
    db.commit()

    return None


@router.post("/{membership_id}/renew", response_model=MembershipResponse)
async def renew_membership(
    membership_id: str,
    extend_days: int = Query(30, ge=1, description="Days to extend the membership"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """
    Renew/extend a membership by adding days to the end_date.

    If the membership is expired, the new period starts from today.
    If active, the days are added to the current end_date.
    """
    membership = db.query(Membership).filter(Membership.id == membership_id).first()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found"
        )

    # If expired, start from today; otherwise extend from current end_date
    base_date = max(membership.end_date, date.today())
    membership.end_date = base_date + timedelta(days=extend_days)
    membership.status = MembershipStatus.ACTIVE.value
    membership.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(membership)

    # Post-commit only — never on a failed/rolled-back write
    await notify_cv_invalidation(str(membership.member_id))

    return membership


@router.get("/member/{member_id}/active", response_model=MembershipResponse)
def get_active_membership(
    member_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """
    Get active membership for a member.
    """
    today = date.today()

    membership = (
        db.query(Membership)
        .filter(
            Membership.member_id == member_id,
            Membership.status == MembershipStatus.ACTIVE.value,
            Membership.start_date <= today,
            Membership.end_date >= today,
        )
        .order_by(Membership.end_date.desc())
        .first()
    )

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No active membership found"
        )

    return membership
