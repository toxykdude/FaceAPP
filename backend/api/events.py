"""
Access Events API endpoints.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, date, timezone

from api.deps import get_db, require_staff
from models.user import User
from models.event import AccessEvent
from schemas.event import (
    AccessEventCreate,
    AccessEventResponse,
    AccessEventListResponse,
    AccessStatsResponse
)

router = APIRouter(prefix="/events", tags=["Access Events"])


@router.get("", response_model=AccessEventListResponse)
def list_events(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    camera_id: Optional[str] = None,
    member_id: Optional[str] = None,
    access_granted: Optional[bool] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff)
):
    """
    List all access events with pagination and filtering.
    
    - **skip**: Number of records to skip
    - **limit**: Maximum number of records to return
    - **camera_id**: Filter by camera ID
    - **member_id**: Filter by member ID
    - **access_granted**: Filter by access granted status
    - **start_date**: Filter events from this timestamp
    - **end_date**: Filter events until this timestamp
    """
    query = db.query(AccessEvent)
    
    # Filter by camera
    if camera_id:
        query = query.filter(AccessEvent.camera_id == camera_id)
    
    # Filter by member
    if member_id:
        query = query.filter(AccessEvent.member_id == member_id)
    
    # Filter by access granted
    if access_granted is not None:
        query = query.filter(AccessEvent.access_granted == access_granted)
    
    # Filter by date range
    if start_date:
        query = query.filter(AccessEvent.timestamp >= start_date)
    if end_date:
        query = query.filter(AccessEvent.timestamp <= end_date)
    
    # Get total count
    total = query.count()
    
    # Get paginated results
    events = query.order_by(AccessEvent.timestamp.desc()).offset(skip).limit(limit).all()
    
    return {
        "total": total,
        "events": events
    }


@router.post("", response_model=AccessEventResponse, status_code=status.HTTP_201_CREATED)
def create_event(
    event: AccessEventCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new access event.
    
    This endpoint is called by the CV service during recognition.
    No authentication required for CV service.
    """
    # Create event
    db_event = AccessEvent(
        camera_id=event.camera_id,
        member_id=event.member_id,
        confidence_score=event.confidence_score,
        access_granted=event.access_granted,
        denial_reason=event.denial_reason,
        frame_snapshot_path=event.frame_snapshot_path
    )
    
    db.add(db_event)
    
    # Update member last_seen
    if event.member_id:
        from models.member import Member
        member = db.query(Member).filter(Member.id == event.member_id).first()
        if member:
            member.last_seen = datetime.now(timezone.utc)
    
    # Update camera last_seen
    if event.camera_id:
        from models.camera import Camera
        camera = db.query(Camera).filter(Camera.id == event.camera_id).first()
        if camera:
            camera.last_seen = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(db_event)
    
    return db_event


# IMPORTANT: Static routes like /today-recognized and /stats/summary
# MUST be defined BEFORE the /{event_id} parameterized route.


@router.get("/today-recognized")
def get_today_recognized(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """Get today recognized members with their membership status."""
    from models.member import Member
    from models.membership import Membership
    
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Get all access events with member_id from today
    events = db.query(AccessEvent).filter(
        AccessEvent.member_id.isnot(None),
        AccessEvent.timestamp >= today_start
    ).order_by(AccessEvent.timestamp.desc()).all()
    
    # Deduplicate by member_id, keep latest event
    seen = set()
    result = []
    for evt in events:
        mid = str(evt.member_id)
        if mid in seen:
            continue
        seen.add(mid)
        
        member = db.query(Member).filter(Member.id == evt.member_id).first()
        if not member:
            continue
        
        # Get latest membership
        latest_membership = db.query(Membership).filter(
            Membership.member_id == evt.member_id
        ).order_by(Membership.end_date.desc()).first()
        
        result.append({
            "member_id": mid,
            "member_name": f"{member.first_name} {member.last_name}",
            "member_id_number": member.id_number,
            "membership_status": latest_membership.status if latest_membership else "none",
            "membership_plan": latest_membership.type if latest_membership else None,
            "membership_end": latest_membership.end_date.isoformat() if latest_membership and latest_membership.end_date else None,
            "last_seen": evt.timestamp.isoformat(),
            "confidence": evt.confidence_score,
        })
    
    return {"recognized": result}


@router.get("/stats/summary", response_model=AccessStatsResponse)
def get_access_stats(
    camera_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff)
):
    """
    Get access statistics.
    
    - **camera_id**: Filter by camera ID (optional)
    - **start_date**: Stats start date (optional)
    - **end_date**: Stats end date (optional)
    """
    query = db.query(AccessEvent)
    
    # Filter by camera
    if camera_id:
        query = query.filter(AccessEvent.camera_id == camera_id)
    
    # Filter by date range
    if start_date:
        query = query.filter(AccessEvent.timestamp >= start_date)
    if end_date:
        query = query.filter(AccessEvent.timestamp <= end_date)
    
    # Get total events
    total_events = query.count()
    
    # Get granted/denied counts
    granted_count = query.filter(AccessEvent.access_granted == True).count()
    denied_count = query.filter(AccessEvent.access_granted == False).count()
    
    # Calculate grant rate
    grant_rate = (granted_count / total_events * 100) if total_events > 0 else 0.0
    
    # Get denial reasons distribution
    denial_reasons = {}
    denied_events = query.filter(AccessEvent.access_granted == False).all()
    
    for event in denied_events:
        reason = event.denial_reason or "unknown"
        denial_reasons[reason] = denial_reasons.get(reason, 0) + 1
    
    return {
        "total_events": total_events,
        "granted_count": granted_count,
        "denied_count": denied_count,
        "grant_rate": round(grant_rate, 2),
        "denial_reasons": denial_reasons
    }


@router.get("/{event_id}", response_model=AccessEventResponse)
def get_event(
    event_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff)
):
    """
    Get access event by ID.
    """
    event = db.query(AccessEvent).filter(AccessEvent.id == event_id).first()
    
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    
    return event
