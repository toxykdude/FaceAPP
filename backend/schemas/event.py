"""
Pydantic schemas for Access Events.
"""
from pydantic import BaseModel, Field, field_serializer
from typing import Optional, List, Any
from datetime import datetime


class AccessEventBase(BaseModel):
    """Base access event schema."""
    camera_id: str
    member_id: Optional[str] = None
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    access_granted: bool
    denial_reason: Optional[str] = None


class AccessEventCreate(AccessEventBase):
    """Schema for creating an access event."""
    pass


class AccessEventResponse(AccessEventBase):
    """Schema for access event response."""
    id: Any
    timestamp: datetime
    frame_snapshot_path: Optional[str] = None
    
    @field_serializer('id')
    def serialize_id(self, value: Any) -> str:
        """Convert UUID to string."""
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
