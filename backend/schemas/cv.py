"""
CV internal API response schemas.
"""
from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class TemplateResponse(BaseModel):
    member_id: str
    name: str
    status: str
    embedding: List[float]
    quality_score: Optional[float] = None
    has_active_membership: bool
    membership_status: Optional[str] = None
    membership_end_date: Optional[str] = None
    access_rules: Dict[str, Any] = {}

    class Config:
        from_attributes = True


class TemplateSyncResponse(BaseModel):
    total: int
    templates: List[TemplateResponse]


class MembershipCheckResponse(BaseModel):
    has_active: bool
    membership: Optional[Dict[str, Any]] = None


class MemberInternalResponse(BaseModel):
    id: str
    first_name: str
    last_name: str
    full_name: Optional[str] = None
    status: str
    facial_data_enrolled: bool


class CameraInternalResponse(BaseModel):
    id: str
    name: str
    rtsp_url: Optional[str] = None
    fps: int = 5
    location: Optional[str] = None
    confidence_threshold: float = 0.85


class CameraListResponse(BaseModel):
    total: int
    cameras: List[CameraInternalResponse]
