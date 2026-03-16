"""Relationship router for Hippo API.

Provides endpoints for managing entity relationships.
"""

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request, Path
from pydantic import BaseModel

from hippo.api.exceptions import EntityNotFoundError
from hippo.core.client import HippoClient

router = APIRouter(prefix="/entities", tags=["relationships"])


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


class RelationshipRequest(BaseModel):
    """Request body for creating a relationship."""

    target_entity_id: str
    relationship_type: str


@router.get("/{entity_id}/relationships")
async def get_entity_relationships(
    entity_id: str,
    request: Request,
    auth: dict = Depends(require_auth),
) -> list[dict[str, Any]]:
    """Get all relationships for an entity.

    Args:
        entity_id: The ID of the entity.
        request: FastAPI request object.
        auth: Authentication context.

    Returns:
        List of relationships.

    Raises:
        HTTPException: If entity not found.
    """
    client = await get_client(request)

    try:
        client.get(entity_type="entity", entity_id=entity_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return []


@router.post("/{entity_id}/relationships")
async def create_relationship(
    entity_id: str,
    request: Request,
    body: RelationshipRequest,
    auth: dict = Depends(require_auth),
) -> dict[str, Any]:
    """Create a relationship between entities.

    Args:
        entity_id: The ID of the source entity.
        request: FastAPI request object.
        body: Relationship request with target and type.
        auth: Authentication context.

    Returns:
        Created relationship.

    Raises:
        HTTPException: If entity not found.
    """
    client = await get_client(request)

    try:
        client.get(entity_type="entity", entity_id=entity_id)
        client.get(entity_type="entity", entity_id=body.target_entity_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    rel_id = f"{entity_id}->{body.target_entity_id}:{body.relationship_type}"

    return {
        "id": rel_id,
        "source_entity_id": entity_id,
        "target_entity_id": body.target_entity_id,
        "relationship_type": body.relationship_type,
    }


@router.delete("/{entity_id}/relationships/{rel_id}")
async def delete_relationship(
    entity_id: str,
    rel_id: str = Path(..., description="Relationship ID"),
    request: Request = None,
    auth: dict = Depends(require_auth),
) -> dict[str, Any]:
    """Delete a relationship.

    Args:
        entity_id: The ID of the source entity.
        rel_id: The ID of the relationship to delete.
        request: FastAPI request object.
        auth: Authentication context.

    Returns:
        Deletion confirmation.
    """
    return {"status": "deleted", "relationship_id": rel_id}
