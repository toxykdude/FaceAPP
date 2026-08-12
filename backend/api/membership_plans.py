"""
Membership Plans API endpoints.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from api.deps import get_db, require_page, require_any_page
from models.user import User
from models.membership import MembershipPlan
from schemas.membership_plan import (
    MembershipPlanCreate,
    MembershipPlanUpdate,
    MembershipPlanResponse,
    MembershipPlanListResponse,
)

router = APIRouter(prefix="/membership-plans", tags=["Membership Plans"])


@router.get("", response_model=MembershipPlanListResponse)
def list_membership_plans(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    active_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_page("memberships", "members")),
):
    """
    List membership plans.

    Read-only, and reachable with the Members page too — assigning a membership
    means picking a plan from this catalog. Managing plans stays on Memberships.
    """
    query = db.query(MembershipPlan)

    if active_only:
        query = query.filter(MembershipPlan.is_active == True)

    total = query.count()
    plans = query.order_by(MembershipPlan.price.asc()).offset(skip).limit(limit).all()

    return {"total": total, "plans": plans}


@router.post(
    "", response_model=MembershipPlanResponse, status_code=status.HTTP_201_CREATED
)
def create_membership_plan(
    plan: MembershipPlanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("memberships")),
):
    """
    Create a new membership plan.
    """
    db_plan = MembershipPlan(
        name=plan.name,
        duration_days=plan.duration_days,
        duration_months=plan.duration_months,
        price=plan.price,
        description=plan.description,
        is_active=plan.is_active,
    )

    db.add(db_plan)
    db.commit()
    db.refresh(db_plan)

    return db_plan


@router.get("/{plan_id}", response_model=MembershipPlanResponse)
def get_membership_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("memberships")),
):
    """
    Get membership plan by ID.
    """
    plan = db.query(MembershipPlan).filter(MembershipPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(404, "Plan not found")
    return plan


@router.put("/{plan_id}", response_model=MembershipPlanResponse)
def update_membership_plan(
    plan_id: str,
    plan_update: MembershipPlanUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("memberships")),
):
    """
    Update membership plan.
    """
    plan = db.query(MembershipPlan).filter(MembershipPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(404, "Plan not found")

    update_data = plan_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(plan, field, value)

    plan.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(plan)
    return plan


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_membership_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("memberships")),
):
    """
    Delete membership plan. If the plan has linked memberships, soft-delete (deactivate) instead.
    """
    plan = db.query(MembershipPlan).filter(MembershipPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(404, "Plan not found")

    # Check if any memberships reference this plan
    from models.membership import Membership

    linked_count = db.query(Membership).filter(Membership.plan_id == plan_id).count()

    if linked_count > 0:
        # Soft-delete: deactivate the plan instead of hard-deleting
        plan.is_active = False
        plan.updated_at = datetime.now(timezone.utc)
        db.commit()
    else:
        db.delete(plan)
        db.commit()
    return None
