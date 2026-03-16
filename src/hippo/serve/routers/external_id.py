"""External ID router for Hippo API.

Provides endpoints for managing external identifiers.
"""

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Path, Request
from pydantic import BaseModel

from hippo.api.exceptions import EntityNotFoundError
from hippo.core.client import HippoClient

router = APIRouter(tags=["external-ids"])


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


class ExternalIdRequest(BaseModel):
    """Request body for registering an external ID."""

    external_id: str


@router.get("/external-ids/{id_type}/{external_id}")
async def get_entity_by_external_id(
    id_type: str = Path(..., description="External ID type"),
    external_id: str = Path(..., description="External ID value"),
    request: Request = None,
    auth: dict = Depends(require_auth),
) -> dict[str, Any]:
    """Get an entity by its external ID.

    Args:
        id_type: The type of external ID.
        external_id: The external ID value.
        request: FastAPI request object.
        auth: Authentication context.

    Returns:
        Entity information.

    Raises:
        HTTPException: If entity not found.
    """
    client = await get_client(request)

    try:
        entity = client.get_by_external_id(external_id=external_id)
        return entity
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/entities/{entity_id}/external-ids")
async def list_entity_external_ids(
    entity_id: str,
    request: Request = None,
    include_superseded: bool = False,
    auth: dict = Depends(require_auth),
) -> list[dict[str, Any]]:
    """List all external IDs for an entity.

    Args:
        entity_id: The ID of the entity.
        request: FastAPI request object.
        include_superseded: Include superseded IDs.
        auth: Authentication context.

    Returns:
        List of external ID records.

    Raises:
        HTTPException: If entity not found.
    """
    client = await get_client(request)

    try:
        external_ids = client.list_external_ids(
            entity_id=entity_id,
            include_superseded=include_superseded,
        )
        return external_ids
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/entities/{entity_id}/external-ids")
async def register_external_id(
    entity_id: str,
    request: Request,
    body: ExternalIdRequest,
    auth: dict = Depends(require_auth),
) -> dict[str, Any]:
    """Register an external ID for an entity.

    Args:
        entity_id: The ID of the entity.
        request: FastAPI request object.
        body: External ID registration request.
        auth: Authentication context.

    Returns:
        Created external ID record.

    Raises:
        HTTPException: If entity not found.
    """
    client = await get_client(request)

    try:
        result = client.register_external_id(
            entity_id=entity_id,
            external_id=body.external_id,
        )
        return result
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
