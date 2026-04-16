"""
Pydantic schemas for enrollment request queue (remote Android enrollment).
"""
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field, field_serializer


class EnrollmentRequestCreate(BaseModel):
    """Admin creates a new enrollment request for the tablet."""
    member_id: str
    device_id: str = "kiosk-android"


class EnrollmentRequestResponse(BaseModel):
    """Enrollment request status (returned to both frontend and Android)."""
    id: Any
    member_id: Any
    member_name: Optional[str] = None
    device_id: str
    status: str  # pending, processing, complete, failed, cancelled
    quality_score: Optional[float] = None
    result_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @field_serializer('id', 'member_id')
    def serialize_uuid(self, value: Any) -> str:
        return str(value)

    class Config:
        from_attributes = True


class EnrollmentStartRequest(BaseModel):
    """Android marks request as processing."""
    pass  # No body needed


class EnrollmentCompleteRequest(BaseModel):
    """Android marks request as complete with result."""
    success: bool
    quality_score: Optional[float] = None
    message: Optional[str] = None
