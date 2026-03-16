"""Search router for Hippo API.

Provides endpoints for full-text search of entities.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from hippo.core.client import HippoClient

router = APIRouter(prefix="/search", tags=["search"])


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


@router.get("")
async def search_entities(
    request: Request,
    entity_type: str = Query(..., description="Entity type to search"),
    q: str = Query(..., description="Search query"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Results to skip"),
    auth: dict = Depends(require_auth),
) -> list[dict[str, Any]]:
    """Search entities using full-text search.

    Args:
        request: FastAPI request object.
        entity_type: The entity type to search.
        q: The search query string.
        limit: Maximum number of results.
        offset: Number of results to skip.
        auth: Authentication context.

    Returns:
        List of matching entities.
    """
    client = await get_client(request)

    results = client.search(
        entity_type=entity_type,
        query=q,
        limit=limit,
    )

    return results[offset : offset + limit]
