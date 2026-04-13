"""
Internal CV API endpoints.

These endpoints are used by the CV service for template sync and access validation.
They are NOT authenticated because the CV service is a trusted internal service
running on the same server, communicating via localhost.
"""
import json
import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from api.deps import get_db
from models.member import Member
from models.biometric import BiometricTemplate
from models.membership import Membership, MembershipStatus
from models.camera import Camera
from core.encryption import decrypt_template, decrypt_string

router = APIRouter(prefix="/cv", tags=["CV Internal"])


@router.get("/templates")
def sync_templates(db: Session = Depends(get_db)):
    """
    Return all enrolled member templates for CV service to load into Redis.
    
    Each template includes the decrypted FaceNet embedding and member metadata.
    Called by CV service on startup and periodically for refresh.
    """
    # Get all enrolled members with their templates and active memberships
    templates = db.query(
        BiometricTemplate,
        Member,
        Membership
    ).join(
        Member, BiometricTemplate.member_id == Member.id
    ).outerjoin(
        Membership,
        (Membership.member_id == Member.id) &
        (Membership.status == MembershipStatus.ACTIVE.value)
    ).filter(
        Member.status == "active"
    ).all()
    
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


@router.get("/members/{member_id}/membership")
def get_member_membership(
    member_id: str,
    db: Session = Depends(get_db)
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


@router.get("/members/{member_id}")
def get_member_internal(
    member_id: str,
    db: Session = Depends(get_db)
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


@router.get("/cameras")
def get_enabled_cameras(db: Session = Depends(get_db)):
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
