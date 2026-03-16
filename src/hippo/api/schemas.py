"""API schemas for Hippo."""

from typing import Optional

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Standard error response format for Hippo API."""

    error: str
    detail: Optional[str] = None
