"""Availability router for Hippo API.

Provides endpoints for managing entity availability.
"""

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from hippo.api.exceptions import EntityNotFoundError
from hippo.core.client import HippoClient

router = APIRouter(prefix="/entities", tags=["availability"])


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


class AvailabilityRequest(BaseModel):
    """Request body for availability change."""

    is_available: bool


@router.get("/{entity_id}/availability")
async def get_entity_availability(
    entity_id: str,
    request: Request,
    auth: dict = Depends(require_auth),
) -> dict[str, Any]:
    """Get the availability status of an entity.

    Args:
        entity_id: The ID of the entity.
        request: FastAPI request object.
        auth: Authentication context.

    Returns:
        Availability information.

    Raises:
        HTTPException: If entity not found.
    """
    client = await get_client(request)

    try:
        entity = client.get(entity_type="entity", entity_id=entity_id)
        return {
            "entity_id": entity_id,
            "is_available": True,
        }
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{entity_id}/availability")
async def set_entity_availability(
    entity_id: str,
    request: Request,
    body: AvailabilityRequest,
    auth: dict = Depends(require_auth),
) -> dict[str, Any]:
    """Set the availability status of an entity.

    Args:
        entity_id: The ID of the entity.
        request: FastAPI request object.
        body: Availability request with is_available flag.
        auth: Authentication context.

    Returns:
        Updated availability information.

    Raises:
        HTTPException: If entity not found.
    """
    client = await get_client(request)

    try:
        entity = client.get(entity_type="entity", entity_id=entity_id)

        if not body.is_available:
            client.delete(entity_type="entity", entity_id=entity_id)

        return {
            "entity_id": entity_id,
            "is_available": body.is_available,
        }
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
