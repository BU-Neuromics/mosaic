"""Entity router for Hippo API.

Provides endpoints for CRUD operations on entities.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from hippo.api.exceptions import EntityNotFoundError
from hippo.core.client import HippoClient

router = APIRouter(prefix="/entities", tags=["entities"])


async def get_client(request: Request) -> HippoClient:
    """Get the HippoClient from request state.

    Args:
        request: FastAPI request object.

    Returns:
        HippoClient instance.
    """
    if hasattr(request.app.state, "hippo_client"):
        return request.app.state.hippo_client
    return HippoClient()


async def require_auth(authorization: Optional[str] = Header(None)) -> dict:
    """Require authentication for protected endpoints.

    Args:
        authorization: Authorization header value.

    Returns:
        Auth context dict with user info.

    Raises:
        HTTPException: If authorization header is missing or invalid.
    """
    if authorization is None:
        raise HTTPException(status_code=401, detail="Unauthorized access")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized access")

    return {"user_id": "default"}


@router.get("")
async def list_entities(
    request: Request,
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    auth: dict = Depends(require_auth),
) -> list[dict[str, Any]]:
    """List entities with optional filtering and pagination.

    Args:
        request: FastAPI request object.
        entity_type: Optional entity type filter.
        limit: Maximum number of results to return.
        offset: Number of results to skip.
        auth: Authentication context.

    Returns:
        List of entity objects.
    """
    client = await get_client(request)

    filters = []
    if entity_type:
        filters.append({"field": "entity_type", "operator": "eq", "value": entity_type})

    results = client.query(
        entity_type=entity_type or "entity",
        filters=filters,
        limit=limit,
        offset=offset,
    )

    return results


@router.get("/{entity_id}")
async def get_entity(
    entity_id: str,
    request: Request,
    expand: Optional[str] = Query(None, description="Expand related entities"),
    auth: dict = Depends(require_auth),
) -> dict[str, Any]:
    """Get an entity by ID.

    Args:
        entity_id: The ID of the entity to retrieve.
        request: FastAPI request object.
        expand: Optional expand path for related entities.
        auth: Authentication context.

    Returns:
        Entity object with all fields.

    Raises:
        HTTPException: If entity not found.
    """
    client = await get_client(request)

    try:
        entity = client.get(
            entity_type="entity",
            entity_id=entity_id,
            expand=expand,
        )
        return entity
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{entity_id}")
async def delete_entity(
    entity_id: str,
    request: Request,
    auth: dict = Depends(require_auth),
) -> dict[str, Any]:
    """Delete an entity (soft delete).

    Args:
        entity_id: The ID of the entity to delete.
        request: FastAPI request object.
        auth: Authentication context.

    Returns:
        Deletion confirmation.

    Raises:
        HTTPException: If entity not found.
    """
    client = await get_client(request)

    try:
        client.delete(entity_type="entity", entity_id=entity_id)
        return {"status": "deleted", "entity_id": entity_id}
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
