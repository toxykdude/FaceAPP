"""
Pydantic schemas for Access Events.
"""
from pydantic import BaseModel, Field, field_serializer
from typing import Optional, List, Any
from datetime import datetime


class AccessEventBase(BaseModel):
    """Base access event schema."""
    camera_id: Any
    member_id: Optional[Any] = None
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    access_granted: bool
    denial_reason: Optional[str] = None


class AccessEventCreate(AccessEventBase):
    """Schema for creating an access event."""
    frame_snapshot_path: Optional[str] = None


class AccessEventResponse(AccessEventBase):
    """Schema for access event response."""
    id: Any
    timestamp: datetime
    frame_snapshot_path: Optional[str] = None
    
    @field_serializer('id', 'camera_id', 'member_id')
    def serialize_uuid(self, value: Any) -> Optional[str]:
        """Convert UUID to string."""
        if value is None:
            return None
        return str(value)

    class Config:
        from_attributes = True


class AccessEventListResponse(BaseModel):
    """Schema for paginated access event list."""
    total: int
    events: List[AccessEventResponse]


class AccessStatsResponse(BaseModel):
    """Schema for access statistics."""
    total_events: int
    granted_count: int
    denied_count: int
    grant_rate: float
    denial_reasons: dict
