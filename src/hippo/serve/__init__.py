"""Hippo Serve module - REST API transport layer."""

from hippo.api.factory import create_app
from hippo.core.client import HippoClient

from hippo.serve.routers import (
    availability,
    entity,
    external_id,
    health,
    history,
    ingest,
    relationship,
    schema,
    search,
    supersede,
)

__all__ = [
    "create_app",
    "HippoClient",
    "availability",
    "entity",
    "external_id",
    "health",
    "history",
    "ingest",
    "relationship",
    "schema",
    "search",
    "supersede",
]


def create_default_app(hippo_client: HippoClient | None = None):
    """Create the default Hippo API application with all routers.

    Args:
        hippo_client: Optional HippoClient instance.

    Returns:
        Configured FastAPI application.
    """
    routers = [
        health.router,
        entity.router,
        ingest.router,
        search.router,
        history.router,
        availability.router,
        supersede.router,
        relationship.router,
        external_id.router,
        schema.router,
    ]

    return create_app(routers=routers, hippo_client=hippo_client)
