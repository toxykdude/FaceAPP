"""
Import/Export response schemas.
"""

from pydantic import BaseModel
from typing import List


class ImportError(BaseModel):
    row: int
    error: str


class ImportResponse(BaseModel):
    total_rows: int
    created: int
    errors: List[ImportError] = []
