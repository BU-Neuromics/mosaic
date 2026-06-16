"""FastAPI application factory for Hippo."""

import logging
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from hippo.api.exceptions import EntityNotFoundError
from hippo.api.schemas import ErrorResponse
from hippo.core.client import HippoClient
from hippo.core.exceptions import (
    ValidationError as HippoValidationError,
    ValidationFailed,
)
from hippo.core.middleware import PassThroughAuthMiddleware

logger = logging.getLogger(__name__)


def create_app(
    routers: Optional[list] = None,
    hippo_client: Optional[HippoClient] = None,
    title: str = "Hippo API",
    version: Optional[str] = None,
    description: str = (
        "A runtime for LinkML schemas. Generates a typed SDK, REST API, "
        "append-only provenance store, and dynamic validation from a "
        "schema definition."
    ),
    docs_url: str = "/docs",
    redoc_url: str = "/redoc",
    openapi_url: str = "/openapi.json",
) -> FastAPI:
    """Create and configure a FastAPI application.

    Args:
        routers: Optional list of APIRouter instances to mount.
                 Defaults to empty list.
        hippo_client: Optional HippoClient instance for the application.
        title: API title for OpenAPI documentation.
        version: API version for OpenAPI documentation. Defaults to the
            installed Hippo package version.
        description: API description for OpenAPI documentation.
        docs_url: URL path for Swagger UI documentation.
        redoc_url: URL path for ReDoc documentation.
        openapi_url: URL path for OpenAPI schema.

    Returns:
        Configured FastAPI application instance.
    """
    if version is None:
        from hippo import __version__

        version = __version__

    app = FastAPI(
        title=title,
        version=version,
        description=description,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
    )

    if hippo_client:
        app.state.hippo_client = hippo_client

    app.add_exception_handler(
        RequestValidationError,
        lambda request, exc: JSONResponse(
            status_code=422,
            content=ErrorResponse(
                error="Validation Error",
                detail=str(exc),
            ).model_dump(),
        ),
    )

    app.add_exception_handler(
        ValidationError,
        lambda request, exc: JSONResponse(
            status_code=422,
            content=ErrorResponse(
                error="Validation Error",
                detail=str(exc),
            ).model_dump(),
        ),
    )

    app.add_exception_handler(
        EntityNotFoundError,
        lambda request, exc: JSONResponse(
            status_code=404,
            content=ErrorResponse(
                error="Entity Not Found",
                detail=exc.message,
            ).model_dump(),
        ),
    )

    app.add_exception_handler(
        HippoValidationError,
        lambda request, exc: JSONResponse(
            status_code=422,
            content=ErrorResponse(
                error="Validation Error",
                detail=exc.message,
            ).model_dump(),
        ),
    )

    # sec9 §9.9: ValidationFailed carries the full tier-tagged envelope.
    # REST response body includes `passed`, `failures[].tier`,
    # `failures[].rule`, `failures[].field`, `failures[].message`,
    # `failures[].details`. 400 for request-shape issues surfaced
    # through this path; 422 for semantic (CEL / Python) failures.
    def _validation_failed_handler(request: Request, exc: ValidationFailed):
        envelope: dict[str, Any] = {
            "error": "Validation Failed",
            "detail": exc.message,
            "passed": False,
            "failures": [],
        }
        result = getattr(exc, "result", None)
        if result is not None and hasattr(result, "to_envelope"):
            envelope.update(result.to_envelope())
        # 422 for semantic validation failures (sec9 §9.9 boundary rules).
        return JSONResponse(status_code=422, content=envelope)

    app.add_exception_handler(ValidationFailed, _validation_failed_handler)

    async def generic_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error="Internal Server Error",
                detail="An unexpected error occurred",
            ).model_dump(),
        )

    app.add_exception_handler(Exception, generic_exception_handler)

    app.add_middleware(PassThroughAuthMiddleware)

    if routers:
        for router in routers:
            app.include_router(router)

    # When the app is built around a schema-bearing client (as `hippo serve`
    # does via the core factory), enrich the generated OpenAPI document with
    # LinkML-derived per-entity-type components (issue #46). Apps without a
    # client/registry keep the default document.
    registry = getattr(hippo_client, "registry", None) if hippo_client else None
    if registry is not None:
        from hippo.api.openapi import install_typed_openapi

        install_typed_openapi(app, registry)

    return app
