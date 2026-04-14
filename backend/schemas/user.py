"""
Pydantic schemas for User model.
"""
from pydantic import BaseModel, Field, field_serializer
from typing import Optional, Any
from datetime import datetime
from uuid import UUID
from models.user import UserRole


class UserBase(BaseModel):
    """Base user schema."""
    username: str = Field(..., min_length=3, max_length=50)
    email: Optional[str] = None  # Made optional to handle .local domains
    full_name: Optional[str] = None
    role: UserRole = UserRole.STAFF


class UserCreate(UserBase):
    """Schema for creating a user."""
    password: str = Field(..., min_length=8, max_length=100)
    is_active: Optional[bool] = True


class UserUpdate(BaseModel):
    """Schema for updating a user."""
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    permissions: Optional[dict] = None


class UserResponse(UserBase):
    """Schema for user response."""
    id: Any  # Accept UUID or str
    is_active: bool
    permissions: Optional[dict] = None
    created_at: datetime
    last_login: Optional[datetime] = None
    
    @field_serializer('id')
    def serialize_id(self, value: Any) -> str:
        """Convert UUID to string."""
        return str(value)

    @field_serializer('role')
    def serialize_role(self, value: Any) -> str:
        """Normalize role to lowercase string."""
        if isinstance(value, str):
            return value.lower()
        return str(value).lower() if value else 'staff' 
    
    class Config:
        from_attributes = True


class Token(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class TokenData(BaseModel):
    """Token payload data."""
    user_id: Optional[str] = None


class LoginRequest(BaseModel):
    """Login request."""
    username: str
    password: str


class PasswordChange(BaseModel):
    """Password change request."""
    current_password: Optional[str] = None  # Required when changing own password
    new_password: str = Field(..., min_length=8, max_length=100)

