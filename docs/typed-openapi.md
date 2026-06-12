# Typed OpenAPI

Hippo's REST routes are deliberately generic — entity payloads travel as
plain JSON and the entity type is named in the URL, not in a per-type
route. That keeps the transport thin (all typing lives in the schema and
the SDK), but a vanilla generated OpenAPI document would describe every
payload as an opaque object.

Hippo closes that gap by **enriching the OpenAPI document with
schema-derived components**. When the app is built around a configured
client (which is what `hippo serve` does), `/openapi.json` includes one
JSON Schema component per entity type in your LinkML schema, so API
explorers and client generators see the real payload shapes — while the
routes themselves stay generic.

## What gets generated

Given a schema like:

```yaml
classes:
  Project:
    is_a: Entity
    attributes:
      name:
        required: true
  Sample:
    is_a: Entity
    attributes:
      name:
        required: true
      project_id:
        range: Project
      status:
        range: SampleStatus
      volume_ml:
        range: float

enums:
  SampleStatus:
    permissible_values:
      active:
      archived:
      distributed:
```

the served document contains, under `components/schemas`:

- **One component per exposed entity type** (`Project`, `Sample`, ...):
    - User fields with JSON Schema types matching their LinkML ranges
      (`float` → `number`, `datetime` → `string`/`date-time`, ...), with
      schema-required fields listed in `required`.
    - Enum-ranged slots as JSON Schema `enum`s
      (`status: {"enum": ["active", "archived", "distributed"]}`).
    - Reference slots (range is another entity class) as
      `string`/`uuid` properties whose `description` names the target
      type. Multivalued slots become arrays.
    - The stored system fields `id` and `is_available`, and the
      provenance-computed temporal fields `created_at`, `updated_at`,
      `schema_version`, `created_by`, `updated_by` — all marked
      `readOnly: true`, so generated clients exclude them from write
      payloads.
- **`Entity`** — an umbrella `oneOf` over every per-type component.
  Entity payloads carry no inline type property (the type travels in the
  URL path on writes and in the envelope's `entity_type` field on reads),
  so there is no OpenAPI `discriminator`; the class-name → component
  mapping is documented in the umbrella's `description`.
- **`EntityEnvelope`** — the read wrapper returned by entity endpoints:
  `{id, entity_type, data, version, created_at, updated_at}` with `data`
  referencing the `Entity` umbrella.

The generic entity endpoints are wired to these components in the
document: `PUT /entities/{entity_type}/{entity_id}` declares the umbrella
as its request body, and the `GET` endpoints declare `EntityEnvelope`
(single or paginated) as their `200` responses.

All exposure and classification decisions come from
`hippo.core.schema_typing` — the same shared LinkML→type model that
drives the typed SDK — so the OpenAPI surface, the SDK accessors, and any
other transport cannot drift apart. The rendering lives in
`hippo.api.openapi`; the document is built once and cached
(`app.openapi_schema`), and an app constructed without a client/registry
serves the default, unenriched document.

## Browsing the typed surface

Start the server against your schema and open the interactive docs:

```bash
hippo serve --config hippo.yaml
# Swagger UI: http://localhost:8000/docs
# Raw document: http://localhost:8000/openapi.json
```

The per-type schemas appear in the Swagger UI "Schemas" panel, and the
entity endpoints show typed request/response examples.

## Generating typed clients

Because the per-type shapes are ordinary OpenAPI components, standard
generators produce typed models for your deployment's schema.

### datamodel-code-generator (Python / Pydantic)

```bash
pip install datamodel-code-generator
datamodel-codegen \
  --url http://localhost:8000/openapi.json \
  --input-file-type openapi \
  --output hippo_models.py
```

This emits one Pydantic model per entity type (plus the envelope), with
enums, optionality, and datetime fields matching your LinkML schema.

### openapi-generator (many languages)

```bash
# e.g. a TypeScript client
openapi-generator-cli generate \
  -i http://localhost:8000/openapi.json \
  -g typescript-fetch \
  -o ./hippo-client
```

`readOnly` fields are honored by both tools: generated request types omit
the server-managed fields (`id`, `is_available`, temporal fields) while
response types include them.

!!! note "The routes themselves stay generic"
    Enrichment is documentation-only: requests are still dispatched
    through the generic `/entities/...` routes and validated by the SDK's
    schema-driven validation pipeline, not by FastAPI request models.
    Per-entity-type routes (one path per class) are a possible future
    step; the current design keeps the transport schema-agnostic at
    runtime.
