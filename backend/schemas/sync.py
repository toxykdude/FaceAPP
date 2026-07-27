"""
Sync response schemas.
"""

from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime


class SyncPullResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    sync_timestamp: str
    schema_version: int


class SyncConflict(BaseModel):
    entity_type: str
    entity_id: str
    local_updated: datetime
    remote_updated: datetime


class SyncPushResponse(BaseModel):
    results: List[Dict[str, Any]]
    sync_timestamp: str


class SyncStatusResponse(BaseModel):
    server_time: str
    schema_version: int
    tables: Dict[str, Any]


class MessageResponse(BaseModel):
    message: str
