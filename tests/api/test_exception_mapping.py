"""Tests for SDK exception → HTTP status mapping in the API factory.

Every ``MosaicError`` subclass raised by a route must surface as a meaningful
HTTP status with the standard ``ErrorResponse`` body shape (``error`` +
``detail``), not an anonymous 500 (sec4 §4.3).

The not-found and the two validation handlers were already registered on main
(PR #43) and are exercised here too to lock the full surface; the net-new
mappings (409 supersession/config conflict, 400 client-side ingestion/search/
temporal/schema, named 500 adapter/provenance) plus the ``MosaicError`` fallback
are the focus of this change.
"""

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from mosaic.api.factory import create_app
from mosaic.core.exceptions import (
    AdapterError,
    ConfigError,
    EntityAlreadySupersededError,
    EntityNotFoundError,
    IngestionError,
    IngestionValidationError,
    OrchestrationError,
    ProvenanceIntegrityError,
    RecipeFetchError,
    SchemaError,
    SearchCapabilityError,
    TemporalQueryError,
    ValidationError,
    ValidationFailure,
)


def _app_raising(exc: Exception) -> TestClient:
    """Build a test client whose single route raises ``exc``."""
    router = APIRouter()

    @router.get("/boom")
    async def boom():
        raise exc

    app = create_app(routers=[router])
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    ("exc", "expected_status", "expected_error"),
    [
        # --- Already handled on main (PR #43) — locked here for completeness.
        (
            EntityNotFoundError(message="Entity not found: x"),
            404,
            "Entity Not Found",
        ),
        (
            ValidationError(message="bad value", field_name="f"),
            422,
            "Validation Error",
        ),
        # --- Net-new mappings added by this change.
        (
            EntityAlreadySupersededError(
                message="already superseded", entity_id="a", superseded_by="b"
            ),
            409,
            "Entity Already Superseded",
        ),
        (
            ConfigError(message="adapter conflict", field_name="storage"),
            409,
            "Configuration Error",
        ),
        (
            ValidationFailure(message="rule failed", rule_id="r1"),
            422,
            "Validation Failed",
        ),
        (
            IngestionError(message="cannot parse file"),
            400,
            "Ingestion Error",
        ),
        (
            # subclass of IngestionError → inherits the 400 mapping via MRO
            IngestionValidationError(message="missing headers"),
            400,
            "Ingestion Error",
        ),
        (
            SearchCapabilityError(message="fts not enabled", field_name="name"),
            400,
            "Search Capability Error",
        ),
        (
            TemporalQueryError(message="before creation", entity_id="a"),
            400,
            "Temporal Query Error",
        ),
        (
            SchemaError(message="unknown entity type", error_code="E1"),
            400,
            "Schema Error",
        ),
        (
            AdapterError(message="db locked", adapter_name="sqlite"),
            500,
            "Storage Adapter Error",
        ),
        (
            ProvenanceIntegrityError(
                message="missing provenance", entity_id="a"
            ),
            500,
            "Provenance Integrity Error",
        ),
    ],
)
def test_sdk_exception_maps_to_http_status(exc, expected_status, expected_error):
    client = _app_raising(exc)
    response = client.get("/boom")
    assert response.status_code == expected_status
    body = response.json()
    assert body["error"] == expected_error
    assert exc.message in body["detail"]


@pytest.mark.parametrize(
    "exc",
    [
        RecipeFetchError(message="connection refused", source="https://x"),
        OrchestrationError(message="dependency cycle", cycle=["a", "b"]),
    ],
)
def test_unmapped_mosaic_error_falls_back_to_named_500(exc):
    """MosaicError subclasses without a dedicated mapping get a named 500.

    The fallback uses the concrete class name as ``error`` and carries the
    SDK message, so an unmapped error is still attributable — never an
    anonymous 500.
    """
    client = _app_raising(exc)
    response = client.get("/boom")
    assert response.status_code == 500
    body = response.json()
    assert body["error"] == type(exc).__name__
    assert exc.message in body["detail"]


def test_non_mosaic_exception_stays_anonymous_500():
    """Arbitrary exceptions keep the opaque generic handler (no leaking)."""
    client = _app_raising(RuntimeError("secret internal state"))
    response = client.get("/boom")
    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "Internal Server Error"
    assert "secret internal state" not in (body.get("detail") or "")
