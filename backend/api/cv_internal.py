"""
Internal CV API endpoints.

These endpoints are used by the CV service for template sync and access validation.
Protected by a shared secret (X-Internal-Secret header) for defense-in-depth,
in addition to network-level isolation (ports 8000/8001 firewalled from external access).
"""
import json
import numpy as np
from sqlalchemy import func
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import List, Optional

from api.deps import get_db
from models.member import Member
from models.biometric import BiometricTemplate
from models.membership import Membership, MembershipStatus
from models.camera import Camera
from core.encryption import decrypt_template, decrypt_string
from core.config import settings
from schemas.cv import (
    TemplateSyncResponse, MembershipCheckResponse,
    MemberInternalResponse, CameraListResponse,
)

router = APIRouter(prefix="/cv", tags=["CV Internal"])


async def verify_internal_secret(x_internal_secret: str = Header(None, alias="X-Internal-Secret")):
    """
    Verify shared secret for internal service-to-service communication.
    
    Both the backend and CV service share INTERNAL_API_SECRET.
    Requests without the correct header are rejected.
    When the secret is empty (development), all requests are allowed.
    """
    if not settings.INTERNAL_API_SECRET:
        return None  # Development mode: no secret configured
    if x_internal_secret != settings.INTERNAL_API_SECRET:
        raise HTTPException(status_code=401, detail="Invalid internal service credentials")
    return x_internal_secret


@router.get("/templates", response_model=TemplateSyncResponse)
def sync_templates(
    db: Session = Depends(get_db),
    _: str = Depends(verify_internal_secret)
):
    """
    Return all enrolled member templates for CV service to load into Redis.

    Each template includes the decrypted FaceNet embedding and minimal
    member metadata required for recognition display and access validation.

    DISPLAY PREDICATE (not access): status='active' AND end_date>=today —
    deliberately WITHOUT a start_date filter, so a member who paid ahead
    sees their furthest expiration immediately, even before that period
    starts. Ties (same end_date) break on MAX(created_at) then MAX(id) for
    a deterministic single winner per member. Display never grants entry —
    access is validated separately by `get_member_membership` below.

    DATA SENSITIVITY NOTE:
    - `embedding`: 512-dim facial vector (irreversible biometric — GDPR Art. 9)
    - `name`: Required for kiosk recognition overlay display
    - `membership_*`: Required for real-time access validation
    This endpoint is protected by X-Internal-Secret and should ONLY be
    accessible by the CV service via internal network (localhost).
    """
    # Rank each member's active, non-expired memberships by end_date desc,
    # tie-broken by created_at desc then id desc — rn=1 is the deterministic
    # "furthest paid expiration" winner for DISPLAY purposes.
    display_rank = db.query(
        Membership.id.label("membership_id"),
        func.row_number().over(
            partition_by=Membership.member_id,
            order_by=(
                Membership.end_date.desc(),
                Membership.created_at.desc(),
                Membership.id.desc(),
            )
        ).label("rn")
    ).filter(
        Membership.status == MembershipStatus.ACTIVE.value,
        Membership.end_date >= func.current_date(),
    ).subquery()

    display_winning_ids = db.query(display_rank.c.membership_id).filter(
        display_rank.c.rn == 1
    )

    # Get all enrolled members with their templates and DISPLAY membership
    templates = db.query(
        BiometricTemplate,
        Member,
        Membership
    ).join(
        Member, BiometricTemplate.member_id == Member.id
    ).outerjoin(
        Membership,
        (Membership.member_id == Member.id) &
        (Membership.id.in_(display_winning_ids))
    ).filter(
        Member.status == "active"
    ).distinct()
    
    result = []
    for template, member, membership in templates:
        try:
            # Decrypt template
            decrypted = decrypt_template(template.template_data)
            embedding = json.loads(decrypted.decode('utf-8'))
            
            result.append({
                "member_id": str(member.id),
                "name": f"{member.first_name} {member.last_name}",
                "status": member.status,
                "embedding": embedding,
                "quality_score": template.quality_score,
                "has_active_membership": membership is not None,
                "membership_status": membership.status if membership else None,
                "membership_end_date": membership.end_date.isoformat() if membership else None,
                "access_rules": membership.access_rules if membership else {}
            })
        except Exception as e:
            # Log but skip broken templates
            import logging
            logging.getLogger(__name__).error(
                f"Failed to decrypt template for member {member.id}: {e}"
            )
            continue
    
    return {"total": len(result), "templates": result}


@router.get("/members/{member_id}/membership", response_model=MembershipCheckResponse)
def get_member_membership(
    member_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(verify_internal_secret)
):
    """
    Get active membership for a member. Used by CV service for access validation.
    No auth required — internal service endpoint.
    """
    from datetime import date
    
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    membership = db.query(Membership).filter(
        Membership.member_id == member_id,
        Membership.status == MembershipStatus.ACTIVE.value,
        Membership.start_date <= date.today(),
        Membership.end_date >= date.today()
    ).order_by(Membership.end_date.desc()).first()
    
    if not membership:
        return {"has_active": False, "membership": None}
    
    return {
        "has_active": True,
        "membership": {
            "id": str(membership.id),
            "type": membership.type,
            "status": membership.status,
            "start_date": membership.start_date.isoformat(),
            "end_date": membership.end_date.isoformat(),
            "access_rules": membership.access_rules or {}
        }
    }


@router.get("/members/{member_id}", response_model=MemberInternalResponse)
def get_member_internal(
    member_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(verify_internal_secret)
):
    """
    Get member data. Used by CV service for access validation.
    No auth required — internal service endpoint.
    """
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    return {
        "id": str(member.id),
        "first_name": member.first_name,
        "last_name": member.last_name,
        "full_name": member.full_name,
        "status": member.status,
        "facial_data_enrolled": member.facial_data_enrolled
    }


@router.get("/cameras", response_model=CameraListResponse)
def get_enabled_cameras(
    db: Session = Depends(get_db),
    _: str = Depends(verify_internal_secret)
):
    """
    Get all enabled cameras with decrypted RTSP URLs.
    Used by CV service to auto-start camera streams.
    No auth required — internal service endpoint.
    """
    cameras = db.query(Camera).filter(Camera.enabled == True).all()
    
    result = []
    for cam in cameras:
        try:
            rtsp_url = decrypt_string(cam.rtsp_url)
        except Exception:
            rtsp_url = None
        
        result.append({
            "id": str(cam.id),
            "name": cam.name,
            "rtsp_url": rtsp_url,
            "fps": cam.fps or 5,
            "location": cam.location,
            "confidence_threshold": cam.confidence_threshold or 0.85
        })
    
    return {"total": len(result), "cameras": result}

