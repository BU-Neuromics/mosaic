"""LinkML-derived OpenAPI components for the REST transport (issue #46).

Approach A: the REST routes stay generic (type-erased ``dict`` payloads),
but the generated OpenAPI document is enriched with one JSON Schema
component per exposed entity type so ``/openapi.json`` describes the real
per-type payload shapes and client generators can emit typed models.

All exposure and classification decisions — which classes are exposed,
how each slot's range classifies (scalar / enum / class-reference), enum
values, required-ness, multivalued-ness, system vs. computed-temporal
fields — come from :mod:`mosaic.core.schema_typing`, the shared
transport-agnostic type model (issue #47). This module only renders that
model into JSON Schema; it makes no schema-interpretation decisions of
its own.

Wiring: :func:`install_typed_openapi` overrides ``app.openapi`` (the
FastAPI convention) so the document is built once, enriched in place, and
cached on ``app.openapi_schema``. Apps without a client/registry are left
untouched and serve the default document.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from mosaic.core.schema_typing import (
    TEMPORAL_FIELDS,
    EntityTypeModel,
    FieldRole,
    SlotKind,
    SlotModel,
    build_type_model,
)

#: Name of the umbrella component covering every exposed entity type.
UMBRELLA_COMPONENT = "Entity"

#: JSON Schema renderings of LinkML scalar ranges. Formats follow the
#: choices made by ``linkml.generators.jsonschemagen`` for the same types;
#: unknown ranges fall back to plain ``string``.
_SCALAR_JSON: dict[str, dict[str, Any]] = {
    "string": {"type": "string"},
    "integer": {"type": "integer"},
    "float": {"type": "number"},
    "double": {"type": "number"},
    "decimal": {"type": "number"},
    "boolean": {"type": "boolean"},
    "date": {"type": "string", "format": "date"},
    "datetime": {"type": "string", "format": "date-time"},
    "time": {"type": "string", "format": "time"},
    "uri": {"type": "string", "format": "uri"},
    "uriorcurie": {"type": "string", "format": "uri"},
    "curie": {"type": "string"},
    "ncname": {"type": "string"},
}

#: JSON Schema for the read-time temporal fields computed from the
#: provenance log (sec9 §9.7). Not stored slots; always read-only.
_TEMPORAL_JSON: dict[str, dict[str, Any]] = {
    "created_at": {"type": "string", "format": "date-time"},
    "updated_at": {"type": "string", "format": "date-time"},
    "schema_version": {"type": "string"},
    "created_by": {"type": "string"},
    "updated_by": {"type": "string"},
}


def _slot_schema(slot: SlotModel) -> dict[str, Any]:
    """Render one :class:`SlotModel` as a JSON Schema property."""
    if slot.kind is SlotKind.ENUM:
        schema: dict[str, Any] = {
            "type": "string",
            "enum": list(slot.enum_values),
        }
    elif slot.kind is SlotKind.REFERENCE:
        schema = {
            "type": "string",
            "format": "uuid",
            "description": f"Reference (entity id) to a {slot.target_class} entity.",
        }
    elif slot.kind is SlotKind.STRUCTURED:
        # Inline structured value type (issue #48). Currently the only
        # value type is ExternalReference; render its known shape.
        schema = {
            "type": "object",
            "title": slot.target_class or slot.range,
            "properties": {
                "system": {
                    "type": "string",
                    "description": "External system that owns the identifier.",
                },
                "value": {
                    "type": "string",
                    "description": "Identifier as it appears in `system`.",
                },
                "retrieved_at": {"type": "string", "format": "date-time"},
                "version": {"type": "string"},
            },
            "required": ["system", "value"],
            "description": (
                f"Inline {slot.target_class or slot.range} value (stored on "
                "the entity, not a separate entity)."
                + (
                    " Reverse-lookup key: (system, value) is globally unique "
                    "among available entities and resolvable via "
                    "GET /xref/{system}/{value}."
                    if slot.is_external_xref
                    else ""
                )
            ),
        }
    else:
        schema = dict(_SCALAR_JSON.get(slot.range, {"type": "string"}))

    if slot.description and "description" not in schema:
        schema["description"] = slot.description

    if slot.multivalued:
        schema = {"type": "array", "items": schema}

    if slot.role is FieldRole.SYSTEM:
        schema["readOnly"] = True

    return schema


def entity_type_component(model: EntityTypeModel) -> dict[str, Any]:
    """Build the JSON Schema component for one exposed entity type.

    User fields are typed and writable; system fields (``id``,
    ``is_available``) and the computed temporal fields are included as
    ``readOnly`` so generated clients omit them from write payloads.
    """
    properties: dict[str, Any] = {}
    required: list[str] = []

    for slot in model.fields:
        properties[slot.name] = _slot_schema(slot)
        if slot.required and slot.role is FieldRole.USER:
            required.append(slot.name)

    for name in TEMPORAL_FIELDS:
        temporal = dict(_TEMPORAL_JSON.get(name, {"type": "string"}))
        temporal["readOnly"] = True
        temporal.setdefault(
            "description",
            "Computed at read time from the provenance log.",
        )
        properties[name] = temporal

    schema: dict[str, Any] = {
        "type": "object",
        "title": model.class_name,
        "properties": properties,
    }
    if model.description:
        schema["description"] = model.description
    if required:
        schema["required"] = required
    return schema


def build_entity_components(registry: Any) -> dict[str, dict[str, Any]]:
    """Build all LinkML-derived components for *registry*.

    Returns a mapping of component name -> JSON Schema: one component per
    exposed entity type plus the :data:`UMBRELLA_COMPONENT` ``oneOf`` over
    them. JSON-payload entity data carries no type-discriminating
    property (the type travels in the URL path or the ``entity_type``
    envelope field), so the umbrella documents the class-name -> component
    mapping in its description instead of an OpenAPI ``discriminator``.
    """
    type_model = build_type_model(registry)
    components: dict[str, dict[str, Any]] = {
        name: entity_type_component(model)
        for name, model in sorted(type_model.items())
    }

    names = sorted(type_model)
    mapping = ", ".join(f"{n} -> #/components/schemas/{n}" for n in names)
    components[UMBRELLA_COMPONENT] = {
        "oneOf": [{"$ref": f"#/components/schemas/{n}"} for n in names],
        "description": (
            "Any exposed entity type, derived from the deployment's LinkML "
            "schema. Entity payloads carry no inline type discriminator — "
            "the type is named by the URL path (write) or the envelope's "
            f"entity_type field (read). Type mapping: {mapping}."
        ),
    }
    return components


def _entity_envelope_schema() -> dict[str, Any]:
    """JSON Schema for the read envelope wrapping entity payloads."""
    return {
        "type": "object",
        "title": "EntityEnvelope",
        "description": (
            "Read envelope returned by entity endpoints: the entity type "
            "name, the typed payload, and provenance-derived metadata."
        ),
        "properties": {
            "id": {"type": "string", "readOnly": True},
            "entity_type": {
                "type": "string",
                "readOnly": True,
                "description": (
                    "Entity class name; selects the matching variant of "
                    f"#/components/schemas/{UMBRELLA_COMPONENT}."
                ),
            },
            "data": {"$ref": f"#/components/schemas/{UMBRELLA_COMPONENT}"},
            "version": {"type": "integer", "readOnly": True},
            "created_at": {
                "type": "string",
                "format": "date-time",
                "readOnly": True,
            },
            "updated_at": {
                "type": "string",
                "format": "date-time",
                "readOnly": True,
            },
        },
    }


def _json_content(schema: dict[str, Any], description: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {"application/json": {"schema": schema}},
    }


def _wire_entity_paths(spec: dict[str, Any]) -> None:
    """Point the generic entity endpoints at the typed components.

    Documentation only: route signatures and runtime behavior are
    untouched; we rewrite the OpenAPI ``paths`` entries so request bodies
    and 200 responses reference the LinkML-derived components.
    """
    paths = spec.get("paths", {})
    umbrella_ref = {"$ref": f"#/components/schemas/{UMBRELLA_COMPONENT}"}
    envelope_ref = {"$ref": "#/components/schemas/EntityEnvelope"}

    put_op = paths.get("/entities/{entity_type}/{entity_id}", {}).get("put")
    if put_op is not None:
        put_op["requestBody"] = {
            "required": True,
            "description": (
                "Full replacement payload for the entity named by "
                "{entity_type}; must match the corresponding "
                f"#/components/schemas/{UMBRELLA_COMPONENT} variant. "
                "readOnly fields are server-managed and ignored on write."
            ),
            "content": {"application/json": {"schema": umbrella_ref}},
        }
        put_op.setdefault("responses", {})["200"] = _json_content(
            envelope_ref, "The replaced entity."
        )

    get_op = paths.get("/entities/{entity_id}", {}).get("get")
    if get_op is not None:
        get_op.setdefault("responses", {})["200"] = _json_content(
            envelope_ref, "The requested entity."
        )

    list_op = paths.get("/entities", {}).get("get")
    if list_op is not None:
        list_op.setdefault("responses", {})["200"] = _json_content(
            {
                "type": "object",
                "properties": {
                    "items": {"type": "array", "items": envelope_ref},
                    "total": {"type": "integer"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                },
            },
            "Paginated entity envelopes.",
        )


def enrich_openapi(spec: dict[str, Any], registry: Any) -> dict[str, Any]:
    """Enrich a generated OpenAPI document with LinkML-derived components.

    Mutates and returns *spec*: injects per-entity-type components (plus
    the umbrella) under ``components/schemas`` and rewires the generic
    entity endpoints to reference them. Existing component names are
    never overwritten — FastAPI-generated models keep precedence.
    """
    schemas = spec.setdefault("components", {}).setdefault("schemas", {})
    for name, component in build_entity_components(registry).items():
        schemas.setdefault(name, component)
    schemas.setdefault("EntityEnvelope", _entity_envelope_schema())
    _wire_entity_paths(spec)
    return spec


def install_typed_openapi(app: FastAPI, registry: Any) -> None:
    """Override ``app.openapi`` to serve the LinkML-enriched document.

    Follows the FastAPI custom-OpenAPI convention: the default generator
    runs once, the result is enriched in place, and the document is cached
    on ``app.openapi_schema`` so subsequent calls are free.
    """
    default_openapi = app.openapi

    def typed_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        # The default generator builds the document and caches it on
        # app.openapi_schema; we enrich that same dict in place.
        spec = default_openapi()
        enrich_openapi(spec, registry)
        app.openapi_schema = spec
        return spec

    app.openapi = typed_openapi  # type: ignore[method-assign]
