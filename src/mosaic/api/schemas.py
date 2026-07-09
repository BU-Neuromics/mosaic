"""API schemas for Mosaic."""

from typing import Optional

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Standard error response format for Mosaic API."""

    error: str
    detail: Optional[str] = None
