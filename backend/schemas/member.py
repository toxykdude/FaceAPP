"""
Pydantic schemas for Member model.
"""
from pydantic import BaseModel, EmailStr, Field, field_serializer
from typing import Optional, Any
from datetime import datetime
from models.member import MemberStatus


class MemberBase(BaseModel):
    """Base member schema."""
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)


class MemberCreate(MemberBase):
    """Schema for creating a member."""
    id_number: Optional[str] = Field(None, max_length=20)
    consent_given: bool = Field(False, description="Consent for biometric data collection")


class MemberUpdate(BaseModel):
    """Schema for updating a member."""
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    id_number: Optional[str] = Field(None, max_length=20)
    status: Optional[MemberStatus] = None


class MemberResponse(MemberBase):
    """Schema for member response."""
    id: Any
    status: str
    facial_data_enrolled: bool
    consent_given_at: Optional[datetime] = None
    id_number: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_seen: Optional[datetime] = None
    
    @field_serializer('id')
    def serialize_id(self, value: Any) -> str:
        """Convert UUID to string."""
        return str(value)

    class Config:
        from_attributes = True


class MemberListResponse(BaseModel):
    """Schema for paginated member list."""
    total: int
    members: list[MemberResponse]


class BiometricStatusResponse(BaseModel):
    """Schema for biometric enrollment status."""
    member_id: str
    enrolled: bool
    quality_score: Optional[float] = None
    enrolled_at: Optional[datetime] = None


class BiometricEnrollmentResponse(BaseModel):
    """Schema for enrollment response."""
    success: bool
    message: str
    quality_score: float
    member_id: str

