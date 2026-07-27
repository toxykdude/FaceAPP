"""
Pydantic schemas for Camera model.
"""

from pydantic import BaseModel, Field, field_serializer
from typing import Optional, List, Any
from datetime import datetime
from uuid import UUID


class CameraBase(BaseModel):
    """Base camera schema."""

    name: str = Field(..., min_length=1, max_length=100)
    rtsp_url: str = Field(..., description="RTSP stream URL (will be encrypted)")
    location: Optional[str] = Field(None, max_length=200)
    location_id: Optional[str] = None
    fps: int = Field(5, ge=1, le=30)
    resolution_width: int = Field(1280, ge=320, le=3840)
    resolution_height: int = Field(720, ge=240, le=2160)
    enabled: bool = True
    confidence_threshold: float = Field(0.85, ge=0.0, le=1.0)


class CameraCreate(CameraBase):
    """Schema for creating a camera."""

    pass


class CameraUpdate(BaseModel):
    """Schema for updating a camera."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    rtsp_url: Optional[str] = None
    location: Optional[str] = Field(None, max_length=200)
    location_id: Optional[str] = None
    fps: Optional[int] = Field(None, ge=1, le=30)
    resolution_width: Optional[int] = Field(None, ge=320, le=3840)
    resolution_height: Optional[int] = Field(None, ge=240, le=2160)
    enabled: Optional[bool] = None
    confidence_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)


class CameraResponse(BaseModel):
    """Schema for camera response."""

    id: UUID
    name: str
    location: Optional[str] = None
    location_id: Optional[str] = None
    fps: int
    resolution_width: int
    resolution_height: int
    enabled: bool
    confidence_threshold: float
    created_at: datetime
    updated_at: datetime
    last_seen: Optional[datetime] = None

    # Note: rtsp_url is NOT included in response for security

    @field_serializer("id")
    def serialize_id(self, value: Any) -> str:
        """Convert UUID to string."""
        return str(value)

    class Config:
        from_attributes = True


class CameraListResponse(BaseModel):
    """Schema for paginated camera list."""

    total: int
    cameras: List[CameraResponse]
