from pydantic import BaseModel
from typing import Any, Optional
from datetime import datetime


class SettingBase(BaseModel):
    key: str
    value: Any
    description: Optional[str] = None
    category: str = "general"


class SettingCreate(SettingBase):
    pass


class SettingUpdate(BaseModel):
    value: Any
    description: Optional[str] = None


class SettingResponse(SettingBase):
    updated_at: datetime

    class Config:
        from_attributes = True
