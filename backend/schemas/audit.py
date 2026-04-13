"""
Pydantic schemas for audit logs.
"""
from pydantic import BaseModel, field_serializer
from typing import Optional, List, Any
from datetime import datetime


class AuditLogResponse(BaseModel):
    """Schema for audit log response."""
    id: Any
    user_id: Optional[Any] = None
    username: Optional[str] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    details: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime
    
    @field_serializer('id', 'user_id')
    def serialize_uuid(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        return str(value)
    
    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    """Paginated audit log list."""
    total: int
    logs: List[AuditLogResponse]
