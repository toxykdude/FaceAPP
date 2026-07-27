from sqlalchemy import Column, String, JSON, DateTime
from sqlalchemy.sql import func
from core.database import Base


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String, primary_key=True, index=True)
    value = Column(JSON, nullable=False)
    description = Column(String, nullable=True)
    category = Column(String, nullable=False, default="general", index=True)
    updated_at = Column(
        DateTime(timezone=True), onupdate=func.now(), default=func.now()
    )
