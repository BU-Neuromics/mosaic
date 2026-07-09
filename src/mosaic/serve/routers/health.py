"""Health check and system status routers for Mosaic API."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from mosaic import __version__
from mosaic.core.client import MosaicClient

router = APIRouter(tags=["health"])


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


@router.get("/health")
async def health_check() -> dict:
    """Health check endpoint.

    Unauthenticated liveness probe — reports nothing about stored data.

    Returns:
        Health status information.
    """
    return {"status": "healthy", "service": "mosaic"}


@router.get("/status")
async def system_status(
    request: Request,
    auth: dict = Depends(require_auth),
) -> dict[str, Any]:
    """System status endpoint (sec4 system endpoints).

    Reports the Mosaic version, active storage adapter, schema version,
    declared entity types, per-type entity counts, and adapter
    capability declarations. Authenticated — unlike ``/health``, the
    response describes the deployment's data.

    Args:
        request: FastAPI request object.
        auth: Authentication context.

    Returns:
        Status summary from :meth:`MosaicClient.status`.
    """
    client = await get_client(request)
    return client.status()


@router.get("/")
async def root() -> dict:
    """Root endpoint.

    Returns:
        API information.
    """
    return {
        "service": "Mosaic API",
        "version": __version__,
        "docs": "/docs",
    }
