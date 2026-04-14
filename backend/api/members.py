"""
Members API endpoints.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from datetime import datetime, timezone

import httpx

from api.deps import get_db, require_staff
from models.user import User
from models.member import Member, MemberStatus
from models.biometric import BiometricTemplate
from schemas.member import (
    MemberCreate,
    MemberUpdate,
    MemberResponse,
    MemberListResponse,
    BiometricStatusResponse
)

router = APIRouter(prefix="/members", tags=["Members"])


async def notify_cv_invalidation(member_id: str):
    """Notify CV service to invalidate a member's cached template."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"http://localhost:8001/invalidate/{member_id}")
    except Exception:
        pass  # CV service might be down, non-critical


@router.get("", response_model=MemberListResponse)
def list_members(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[MemberStatus] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff)
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
    
    # Search by name or email
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Member.first_name.ilike(search_term)) |
            (Member.last_name.ilike(search_term)) |
            (Member.email.ilike(search_term)) |
            (Member.id_number.ilike(search_term))
        )
    
    # Get total count
    total = query.count()
    
    # Get paginated results
    members = query.order_by(Member.created_at.desc()).offset(skip).limit(limit).all()
    
    return {
        "total": total,
        "members": members
    }


@router.post("", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
def create_member(
    member: MemberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff)
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
                detail="Email already registered"
            )
    
    # Create member
    db_member = Member(
        first_name=member.first_name,
        last_name=member.last_name,
        email=member.email,
        phone=member.phone,
        id_number=member.id_number,
        status=MemberStatus.ACTIVE.value,
        consent_given_at=datetime.now(timezone.utc) if member.consent_given else None
    )
    
    db.add(db_member)
    db.commit()
    db.refresh(db_member)
    
    # Audit log
    from core.audit import log_action
    log_action(db, action="create", resource_type="member", resource_id=str(db_member.id), 
               user_id=str(current_user.id), username=current_user.username,
               details={"name": f"{db_member.first_name} {db_member.last_name}"})
    
    return db_member


@router.get("/{member_id}", response_model=MemberResponse)
def get_member(
    member_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff)
):
    """
    Get member by ID.
    """
    member = db.query(Member).filter(Member.id == member_id).first()
    
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found"
        )
    
    return member


@router.put("/{member_id}", response_model=MemberResponse)
async def update_member(
    member_id: str,
    member_update: MemberUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff)
):
    """
    Update member information.
    """
    member = db.query(Member).filter(Member.id == member_id).first()
    
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found"
        )
    
    # Check email uniqueness if updating
    if member_update.email and member_update.email != member.email:
        existing = db.query(Member).filter(Member.email == member_update.email).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
    
    # Update fields
    update_data = member_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "status" and value:
            setattr(member, field, value.value)
        else:
            setattr(member, field, value)
    
    member.updated_at = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(member)
    
    # Audit log
    from core.audit import log_action
    log_action(db, action="update", resource_type="member", resource_id=str(member.id),
               user_id=str(current_user.id), username=current_user.username,
               details={"updated_fields": list(update_data.keys())})
    
    # Invalidate CV cache if member status changed
    if "status" in update_data:
        await notify_cv_invalidation(str(member.id))
    
    return member


@router.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_member(
    member_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff)
):
    """
    Delete a member.
    
    This will also delete associated biometric data (CASCADE).
    """
    member = db.query(Member).filter(Member.id == member_id).first()
    
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found"
        )
    
    # Delete member (biometric template will be deleted via CASCADE)
    db.delete(member)
    db.commit()
    
    # Audit log
    from core.audit import log_action
    log_action(db, action="delete", resource_type="member", resource_id=str(member_id),
               user_id=str(current_user.id), username=current_user.username)
    
    await notify_cv_invalidation(str(member_id))
    
    return None


@router.get("/{member_id}/biometric-status", response_model=BiometricStatusResponse)
def get_biometric_status(
    member_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff)
):
    """
    Get biometric enrollment status for a member.
    """
    member = db.query(Member).filter(Member.id == member_id).first()
    
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found"
        )
    
    # Get biometric template if exists
    template = db.query(BiometricTemplate).filter(
        BiometricTemplate.member_id == member_id
    ).first()
    
    return {
        "member_id": str(member.id),
        "enrolled": member.facial_data_enrolled,
        "quality_score": template.quality_score if template else None,
        "enrolled_at": template.enrolled_at if template else None
    }
