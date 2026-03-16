"""History router for Hippo API.

Provides endpoints for querying entity history/provenance.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from hippo.api.exceptions import EntityNotFoundError
from hippo.core.client import HippoClient

router = APIRouter(prefix="/entities", tags=["history"])


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


@router.get("/{entity_id}/history")
async def get_entity_history(
    entity_id: str,
    request: Request,
    auth: dict = Depends(require_auth),
) -> list[dict[str, Any]]:
    """Get the change history for an entity.

    Args:
        entity_id: The ID of the entity.
        request: FastAPI request object.
        auth: Authentication context.

    Returns:
        List of history records.

    Raises:
        HTTPException: If entity not found.
    """
    client = await get_client(request)

    try:
        history = client.history(entity_id)
        return history
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
