"""Supersede router for Hippo API.

Provides endpoints for managing entity supersession.
"""

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from hippo.api.exceptions import EntityNotFoundError
from hippo.core.client import HippoClient

router = APIRouter(prefix="/entities", tags=["supersede"])


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


class SupersedeRequest(BaseModel):
    """Request body for superseding an entity."""

    old_external_id: str
    new_external_id: str


@router.post("/{entity_id}/supersede")
async def supersede_entity(
    entity_id: str,
    request: Request,
    body: SupersedeRequest,
    auth: dict = Depends(require_auth),
) -> dict[str, Any]:
    """Supersede an entity's external ID with a new one.

    Args:
        entity_id: The ID of the entity.
        request: FastAPI request object.
        body: Supersession request with old and new external IDs.
        auth: Authentication context.

    Returns:
        New external ID record.

    Raises:
        HTTPException: If entity not found.
    """
    client = await get_client(request)

    try:
        result = client.supersede(
            entity_id=entity_id,
            old_external_id=body.old_external_id,
            new_external_id=body.new_external_id,
        )
        return result
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{entity_id}/superseded")
async def get_superseded_entities(
    entity_id: str,
    request: Request,
    auth: dict = Depends(require_auth),
) -> list[dict[str, Any]]:
    """Get superseded external IDs for an entity.

    Args:
        entity_id: The ID of the entity.
        request: FastAPI request object.
        auth: Authentication context.

    Returns:
        List of superseded external IDs.

    Raises:
        HTTPException: If entity not found.
    """
    client = await get_client(request)

    try:
        external_ids = client.list_external_ids(
            entity_id=entity_id,
            include_superseded=True,
        )
        superseded = [eid for eid in external_ids if eid.get("superseded_at")]
        return superseded
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
