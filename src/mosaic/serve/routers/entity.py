"""Entity router for Mosaic API.

Provides endpoints for CRUD operations on entities.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from mosaic.api.exceptions import EntityNotFoundError
from mosaic.core.client import MosaicClient

router = APIRouter(prefix="/entities", tags=["entities"])


async def get_client(request: Request) -> MosaicClient:
    """Get the MosaicClient from request state.

    Args:
        request: FastAPI request object.

    Returns:
        MosaicClient instance.
    """
    if hasattr(request.app.state, "hippo_client"):
        return request.app.state.hippo_client
    return MosaicClient()


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
    filter_mode: str = Query("and", description="Filter composition: 'and' (all match) or 'or' (any match)"),
    updated_since: Optional[str] = Query(
        None,
        description=(
            "Only return entities whose provenance-derived updated_at is "
            "strictly greater than this ISO 8601 timestamp; results are "
            "ordered by updated_at ascending for watermark polling (sec4 §4.5)"
        ),
    ),
    as_of: Optional[str] = Query(None, description="ISO-8601 transaction-time; reconstruct results as the graph stood at this time (sec6 §6.8 / ADR-0001). Omitted = current state."),
    auth: dict = Depends(require_auth),
) -> dict[str, Any]:
    """List entities with optional filtering and pagination.

    Args:
        request: FastAPI request object.
        entity_type: Optional entity type filter (``None`` scans all types).
        limit: Maximum number of results to return.
        offset: Number of results to skip.
        filter_mode: How to combine filters — "and" or "or".
        updated_since: Optional ISO 8601 watermark for polling callers.
        as_of: Optional ISO-8601 transaction-time for as-of reconstruction.
        auth: Authentication context.

    Returns:
        Paginated response envelope with items, total, limit, and offset.
    """
    client = await get_client(request)

    if updated_since is not None:
        # sec4 §4.5 polling path. entity_type stays optional so the
        # watermark filter composes with the issue #44/#49 cross-class
        # scan (None polls across all types).
        paginated = client.query_updated_since(
            entity_type=entity_type,
            since=updated_since,
            limit=limit,
            offset=offset,
        )
    else:
        paginated = client.query(
            entity_type=entity_type,
            filters=[],
            limit=limit,
            offset=offset,
            filter_mode=filter_mode,
            as_of=as_of,
        )

    return {
        "items": paginated.items,
        "total": paginated.total,
        "limit": paginated.limit,
        "offset": paginated.offset,
    }


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

    entity_type = client.resolve_type(entity_id)
    if entity_type is None:
        raise HTTPException(
            status_code=404, detail=f"Entity not found: {entity_id}"
        )

    try:
        entity = client.get(
            entity_type=entity_type,
            entity_id=entity_id,
            expand=expand,
        )
        return entity
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{entity_type}/{entity_id}")
async def replace_entity(
    entity_type: str,
    entity_id: str,
    request: Request,
    auth: dict = Depends(require_auth),
) -> dict[str, Any]:
    """Full replacement of an existing entity (PUT semantics).

    All required fields must be present. Records a 'replaced' provenance
    event. Returns 404 if the entity does not exist.

    Args:
        entity_type: The entity type.
        entity_id: The ID of the entity to replace.
        request: FastAPI request object.
        auth: Authentication context.

    Returns:
        The replaced entity.

    Raises:
        HTTPException: 404 if entity not found, 422 if validation fails.
    """
    client = await get_client(request)
    body = await request.json()

    try:
        result = client.replace(
            entity_type=entity_type,
            entity_id=entity_id,
            data=body,
        )
        return result
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        if "validation" in str(type(e).__name__).lower():
            raise HTTPException(status_code=422, detail=str(e))
        raise


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

    entity_type = client.resolve_type(entity_id)
    if entity_type is None:
        raise HTTPException(
            status_code=404, detail=f"Entity not found: {entity_id}"
        )

    try:
        client.delete(entity_type=entity_type, entity_id=entity_id)
        return {"status": "deleted", "entity_id": entity_id}
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
