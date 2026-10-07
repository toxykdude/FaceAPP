"""
Pydantic schemas for the WiFi captive-portal endpoints.

Consumed by the radius_service (X-Internal-Secret) and, for the session
listing, by admin/staff clients. Denial reasons intentionally share the
kiosk's vocabulary so staff see one set of reasons for door and WiFi.
"""

from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer


class WiFiAuthorizeRequest(BaseModel):
    """RADIUS Access-Request translated by the radius_service."""

    document: str = Field(..., min_length=1, max_length=64, description="Cédula")
    client_mac: Optional[str] = Field(None, max_length=32)
    client_ip: Optional[str] = Field(None, max_length=64)
    nas_ip: Optional[str] = Field(None, max_length=64)


class WiFiAuthorizeResponse(BaseModel):
    allowed: bool
    # Kiosk-vocabulary reason on denial ("member_not_found",
    # "no_active_membership", "unpaid_membership", "device_limit", ...);
    # None on a grant.
    reason: Optional[str] = None
    member_id: Optional[str] = None
    member_name: Optional[str] = None
    plan_name: Optional[str] = None
    membership_end_date: Optional[date] = None
    days_remaining: Optional[int] = None
    # RADIUS attributes the portal should enforce.
    session_timeout_seconds: Optional[int] = None
    idle_timeout_seconds: Optional[int] = None
    acct_interim_interval_seconds: Optional[int] = None
    # Bilingual portal text — the captive portal cannot know the member's
    # language, so the radius_service joins both into the Reply-Message.
    message_es: str
    message_en: str

    @field_serializer("member_id")
    def serialize_member_id(self, value: Optional[UUID]) -> Optional[str]:
        return str(value) if value else None


class WiFiAccountingRequest(BaseModel):
    """RADIUS Accounting-Request translated by the radius_service."""

    # "start" | "interim" | "stop"
    status: str = Field(..., pattern="^(start|interim|stop)$")
    username: str = Field(..., min_length=1, max_length=64)
    acct_session_id: str = Field(..., min_length=1, max_length=128)
    nas_ip: str = Field("", max_length=64)
    framed_ip: Optional[str] = Field(None, max_length=64)
    calling_station_id: Optional[str] = Field(None, max_length=32)
    acct_input_octets: int = Field(0, ge=0)
    acct_output_octets: int = Field(0, ge=0)
    acct_session_time: Optional[int] = Field(None, ge=0)
    acct_terminate_cause: Optional[str] = Field(None, max_length=64)
    event_timestamp: Optional[datetime] = None


class WiFiAccountingResponse(BaseModel):
    recorded: bool
    session_id: Optional[UUID] = None
    member_id: Optional[UUID] = None

    @field_serializer("session_id", "member_id")
    def serialize_ids(self, value: Optional[UUID]) -> Optional[str]:
        return str(value) if value else None


class WiFiSessionResponse(BaseModel):
    """Admin-facing session row (GET /wifi/sessions)."""

    id: UUID
    member_id: Optional[UUID] = None
    username: str
    nas_ip: str
    acct_session_id: str
    framed_ip: Optional[str] = None
    calling_station_id: Optional[str] = None
    acct_input_octets: int
    acct_output_octets: int
    acct_session_time: Optional[int] = None
    started_at: datetime
    last_update_at: datetime
    ended_at: Optional[datetime] = None
    terminate_cause: Optional[str] = None

    @field_serializer("id")
    def serialize_id(self, value: UUID) -> str:
        return str(value)

    class Config:
        from_attributes = True


class WiFiSessionListResponse(BaseModel):
    total: int
    sessions: List[WiFiSessionResponse]
