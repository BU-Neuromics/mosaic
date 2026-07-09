"""LinkML-derived OpenAPI components on /openapi.json (issue #46, approach A).

The REST routes stay generic, but an app built around a schema-bearing
client (as ``mosaic serve`` builds it) serves an OpenAPI document enriched
with one component schema per exposed entity type, derived from
``mosaic.core.schema_typing``. A no-client app keeps the default document.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mosaic.config import MosaicConfig
from mosaic.core.factory import create_client_from_config
from mosaic.serve import create_default_app

_FIXTURE_SCHEMA = (
    Path(__file__).parents[1] / "fixtures" / "schemas" / "sample_schema.yaml"
)


@pytest.fixture()
def spec(tmp_path):
    cfg = MosaicConfig(
        schema_path=str(_FIXTURE_SCHEMA),
        database_url=str(tmp_path / "openapi.db"),
        storage_backend="sqlite",
    )
    client = create_client_from_config(cfg)
    app = create_default_app(client)
    api = TestClient(app)
    resp = api.get("/openapi.json")
    assert resp.status_code == 200
    return resp.json()


def _schemas(spec):
    return spec["components"]["schemas"]


def test_per_type_components_present(spec):
    schemas = _schemas(spec)
    for name in ("Project", "Sample"):
        assert name in schemas, f"missing component for entity type {name}"
        assert schemas[name]["type"] == "object"


def test_user_fields_typed_and_required(spec):
    sample = _schemas(spec)["Sample"]
    props = sample["properties"]

    assert props["name"]["type"] == "string"
    assert props["volume_ml"]["type"] == "number"
    assert props["collected_at"] == {"type": "string", "format": "date-time"}
    # Only the schema-required user fields are required; readOnly system
    # fields are never required (they are absent from write payloads).
    assert sample["required"] == ["name"]


def test_enum_slot_renders_as_json_schema_enum(spec):
    status = _schemas(spec)["Sample"]["properties"]["status"]
    assert status["type"] == "string"
    assert sorted(status["enum"]) == ["active", "archived", "distributed"]


def test_reference_slot_is_uuid_string_naming_target(spec):
    ref = _schemas(spec)["Sample"]["properties"]["project_id"]
    assert ref["type"] == "string"
    assert ref["format"] == "uuid"
    assert "Project" in ref["description"]


def test_system_and_temporal_fields_read_only(spec):
    props = _schemas(spec)["Project"]["properties"]

    # Stored system fields.
    assert props["id"]["readOnly"] is True
    assert props["is_available"]["readOnly"] is True
    assert props["is_available"]["type"] == "boolean"

    # Computed temporal fields (provenance-derived, never stored slots).
    for name in ("created_at", "updated_at", "schema_version",
                 "created_by", "updated_by"):
        assert props[name]["readOnly"] is True, name
    assert props["created_at"]["format"] == "date-time"
    assert props["updated_at"]["format"] == "date-time"


def test_umbrella_entity_one_of_over_exposed_types(spec):
    entity = _schemas(spec)["Entity"]
    refs = {variant["$ref"] for variant in entity["oneOf"]}
    assert "#/components/schemas/Project" in refs
    assert "#/components/schemas/Sample" in refs
    # No inline discriminator property exists on payloads, so the mapping
    # is documented in the description instead.
    assert "Project -> #/components/schemas/Project" in entity["description"]


def test_generic_endpoints_reference_components(spec):
    paths = spec["paths"]

    put = paths["/entities/{entity_type}/{entity_id}"]["put"]
    body_schema = put["requestBody"]["content"]["application/json"]["schema"]
    assert body_schema == {"$ref": "#/components/schemas/Entity"}

    get = paths["/entities/{entity_id}"]["get"]
    ok = get["responses"]["200"]["content"]["application/json"]["schema"]
    assert ok == {"$ref": "#/components/schemas/EntityEnvelope"}

    listing = paths["/entities"]["get"]
    ok = listing["responses"]["200"]["content"]["application/json"]["schema"]
    assert ok["properties"]["items"]["items"] == {
        "$ref": "#/components/schemas/EntityEnvelope"
    }


def test_envelope_data_references_umbrella(spec):
    envelope = _schemas(spec)["EntityEnvelope"]
    assert envelope["properties"]["data"] == {
        "$ref": "#/components/schemas/Entity"
    }


def test_spec_is_cached_and_stable(tmp_path):
    cfg = MosaicConfig(
        schema_path=str(_FIXTURE_SCHEMA),
        database_url=str(tmp_path / "cache.db"),
        storage_backend="sqlite",
    )
    client = create_client_from_config(cfg)
    app = create_default_app(client)
    api = TestClient(app)

    first = api.get("/openapi.json").json()
    second = api.get("/openapi.json").json()
    assert first == second
    # FastAPI caching convention: the enriched document is held on
    # app.openapi_schema, so repeat calls return the same object.
    assert app.openapi() is app.openapi_schema


def test_no_client_app_serves_unmodified_valid_spec():
    app = create_default_app()
    api = TestClient(app)
    resp = api.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert spec["openapi"].startswith("3.")
    schemas = spec.get("components", {}).get("schemas", {})
    assert "Entity" not in schemas
    assert "EntityEnvelope" not in schemas
    assert "Project" not in schemas
