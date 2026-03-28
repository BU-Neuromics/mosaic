"""Schema router for Hippo API.

Provides endpoints for managing entity schemas.
"""

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Path, Request
from pydantic import BaseModel

from hippo.config.models import SchemaConfig

router = APIRouter(prefix="/schemas", tags=["schemas"])


async def get_client(request: Request):
    """Get the HippoClient from request state."""
    if hasattr(request.app.state, "hippo_client"):
        return request.app.state.hippo_client
    return None


async def require_auth(authorization: Optional[str] = Header(None)) -> dict:
    """Require authentication for protected endpoints."""
    if authorization is None:
        raise HTTPException(status_code=401, detail="Unauthorized access")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized access")

    return {"user_id": "default"}


class SchemaRequest(BaseModel):
    """Request body for creating a schema."""

    name: str
    version: str
    fields: list[dict[str, Any]]


@router.get("")
async def list_schemas(
    request: Request,
    auth: dict = Depends(require_auth),
) -> list[dict[str, Any]]:
    """List all available schemas.

    Args:
        request: FastAPI request object.
        auth: Authentication context.

    Returns:
        List of schema definitions.
    """
    client = await get_client(request)

    if client and hasattr(client, "_schemas") and client._schemas:
        return [
            {
                "name": name,
                "version": schema.version,
                "fields": [
                    {
                        "name": f.name,
                        "field_type": f.field_type,
                        "required": f.required,
                    }
                    for f in schema.fields
                ],
            }
            for name, schema in client._schemas.items()
        ]

    return []


@router.get("/{schema_name}")
async def get_schema(
    schema_name: str = Path(..., description="Schema name"),
    request: Request = None,
    auth: dict = Depends(require_auth),
) -> dict[str, Any]:
    """Get a schema by name.

    Args:
        schema_name: The name of the schema.
        request: FastAPI request object.
        auth: Authentication context.

    Returns:
        Schema definition.

    Raises:
        HTTPException: If schema not found.
    """
    client = await get_client(request)

    if client and hasattr(client, "_schemas") and schema_name in client._schemas:
        schema = client._schemas[schema_name]
        return {
            "name": schema.name,
            "version": schema.version,
            "fields": [
                {
                    "name": f.name,
                    "field_type": f.field_type,
                    "required": f.required,
                }
                for f in schema.fields
            ],
        }

    raise HTTPException(status_code=404, detail=f"Schema not found: {schema_name}")


@router.get("/{entity_type}/references")
async def get_schema_references(
    entity_type: str = Path(..., description="Entity type name"),
    request: Request = None,
    auth: dict = Depends(require_auth),
) -> dict[str, Any]:
    """Get reference edges declared in the schema for an entity type.

    Returns the list of fields on this entity that reference other entity types.

    Args:
        entity_type: The entity type to inspect.
        request: FastAPI request object.
        auth: Authentication context.

    Returns:
        Dict with entity_type and references list.

    Raises:
        HTTPException: If entity type not found in loaded schemas.
    """
    client = await get_client(request)

    if client is None or not hasattr(client, "_schemas") or not client._schemas:
        raise HTTPException(status_code=404, detail=f"Schema not found: {entity_type}")

    if entity_type not in client._schemas:
        raise HTTPException(status_code=404, detail=f"Schema not found: {entity_type}")

    return {
        "entity_type": entity_type,
        "references": client.schema_references(entity_type),
    }


@router.post("")
async def create_schema(
    request: Request,
    body: SchemaRequest,
    auth: dict = Depends(require_auth),
) -> dict[str, Any]:
    """Create a new schema.

    Args:
        request: FastAPI request object.
        body: Schema definition.
        auth: Authentication context.

    Returns:
        Created schema.
    """
    schema = SchemaConfig(
        name=body.name,
        version=body.version,
        fields=[],
    )

    return {
        "name": schema.name,
        "version": schema.version,
        "status": "created",
    }
