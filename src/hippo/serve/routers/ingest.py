"""Ingest router for Hippo API.

Provides endpoints for creating entities.
"""

import json
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ValidationError

from hippo.api.exceptions import EntityNotFoundError
from hippo.core.client import HippoClient
from hippo.core.exceptions import ValidationFailure

router = APIRouter(prefix="/ingest", tags=["ingest"])


async def get_client(request: Request) -> HippoClient:
    """Get the HippoClient from request state."""
    if hasattr(request.app.state, "hippo_client"):
        return request.app.state.hippo_client
    return HippoClient()


async def require_auth(authorization: Optional[str] = Header(None)) -> dict:
    """Require authentication for protected endpoints."""
    if authorization is None:
        raise HTTPException(status_code=401, detail="Unauthorized access")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized access")

    return {"user_id": "default"}


class IngestRequest(BaseModel):
    """Request body for entity ingestion."""

    entity_type: str
    data: dict[str, Any]


@router.post("")
async def ingest_entity(
    request: Request,
    body: dict[str, Any] = Body(...),
    auth: dict = Depends(require_auth),
) -> dict[str, Any]:
    """Create a new entity.

    Args:
        request: FastAPI request object.
        body: Entity data containing entity_type and data fields.
        auth: Authentication context.

    Returns:
        Created entity with generated ID and timestamps.

    Raises:
        HTTPException: If validation fails or entity type is missing.
    """
    if not body:
        raise HTTPException(status_code=400, detail="Invalid JSON format")

    entity_type = body.get("entity_type")
    data = body.get("data", {})

    if not entity_type:
        raise HTTPException(
            status_code=422, detail="Missing required field: entity_type"
        )

    if not data:
        raise HTTPException(status_code=422, detail="Missing required field: data")

    client = await get_client(request)

    try:
        result = client.create(entity_type=entity_type, data=data)
        return result
    except ValidationFailure as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON format: {str(e)}")
