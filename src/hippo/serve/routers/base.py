"""Base router class with authentication for Hippo API."""

import logging
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


async def require_auth(
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
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

    token = authorization[7:]

    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized access")

    return {"user_id": "default", "token": token}


def create_base_router(
    path_prefix: str = "",
    auth_required: bool = True,
) -> tuple[APIRouter, Callable[[dict[str, Any]], Any]]:
    """Create a base router with optional authentication.

    Args:
        path_prefix: Prefix for all routes in this router.
        auth_required: Whether authentication is required.

    Returns:
        Tuple of (router, auth_dependency).
    """
    router = APIRouter(prefix=path_prefix)

    if auth_required:
        auth_dep = Depends(require_auth)
    else:

        async def no_auth():
            return {"user_id": "anonymous", "token": None}

        auth_dep = Depends(no_auth)

    return router, auth_dep


def get_client_from_request(request: Request) -> Any:
    """Get the HippoClient from request state.

    Args:
        request: FastAPI request object.

    Returns:
        HippoClient instance.
    """
    if hasattr(request.app.state, "hippo_client"):
        return request.app.state.hippo_client
    return None
