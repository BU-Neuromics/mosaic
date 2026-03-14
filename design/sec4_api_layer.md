## 4. API Layer

**Document status:** Draft v0.1
**Depends on:** sec2_architecture.md, sec3_data_model.md, sec6_provenance.md
**Feeds into:** sec5_ingestion.md, sec7_nfr.md

---

### 4.1 Design Philosophy

The API layer is SDK-first. All business logic lives in the Core SDK (`HippoClient`). The
REST API is a thin transport adapter that calls the SDK — it contains no logic of its own.
This means the SDK and REST API are always in sync, and the REST API is never "ahead" of the
SDK in capability.

The public surface of the API layer is:
1. **`HippoClient`** — the Python SDK public interface (primary)
2. **REST API** — JSON over HTTP, auto-documented via OpenAPI (secondary; for non-Python callers)

GraphQL is reserved for a future version.

---

### 4.2 HippoClient Public Interface

`HippoClient` is the single entry point to all Hippo functionality. It is instantiated once
with a `HippoConfig` and used throughout the application lifetime.

```python
from hippo import HippoClient, HippoConfig

client = HippoClient(HippoConfig.from_file("hippo.yaml"))
```

#### Entity operations

```python
# Create or update an entity (upsert semantics — see sec5 §5.4)
entity = client.put(
    entity_type="Sample",
    data={"tissue_type": "brain", "external_ids": [{"system": "starlims", "id": "SL-123"}]},
    actor="pipeline-run-42",
    provenance_context={"workflow_run_id": "wf-abc"}  # optional
)
# Returns the written entity dict including system fields

# Fetch by Hippo UUID
sample = client.get("Sample", "uuid-here")

# Fetch by ExternalID
sample = client.get_by_external_id("Sample", system="starlims", external_id="SL-123")

# Fetch multiple by UUID (batch)
samples = client.get_many("Sample", ids=["uuid-1", "uuid-2", "uuid-3"])
```

#### Query operations

```python
# Filter query
results = client.query(
    "Sample",
    tissue_type="brain",
    is_available=True,           # default; pass False to include unavailable
    exact_type=False,            # default; pass True to exclude subtypes
    limit=100,
    offset=0,
    order_by="created_at",
    order_dir="desc"
)
# Returns PaginatedResult (see §4.4)

# Fuzzy search on indexed fields
matches = client.search(
    entity_type="AnatomyTerm",
    field="preferred_label",
    query="prefrontal cortex",
    limit=5,
    min_score=0.5
)
# Returns list[ScoredMatch]

# Graph traversal: follow a named relationship
subjects = client.traverse(
    start_type="Sample", start_id="sample-uuid",
    relationship="donated",
    direction="inbound",   # "outbound" | "inbound" | "both"
    target_type="Subject"  # optional filter
)

# Fetch updated since a timestamp (used by Cappella hippo_poll trigger)
recent = client.query_updated_since(
    entity_type="Sample",
    since="2024-01-01T00:00:00Z",
    limit=500
)
```

#### Availability and lifecycle operations

```python
# Mark unavailable
client.set_availability(
    entity_type="Sample", entity_id="uuid",
    available=False,
    reason="Sample quality insufficient",
    actor="data-team"
)

# Supersede one entity with another
client.supersede(
    entity_type="Sample",
    old_id="old-uuid", new_id="new-uuid",
    actor="pipeline-run-42",
    reason="Corrected tissue region annotation"
)
```

#### Relationship operations

```python
# Create a relationship
client.relate(
    relationship="donated",
    from_type="Subject", from_id="subj-uuid",
    to_type="Sample",   to_id="sample-uuid",
    actor="data-team",
    properties={"method": "surgical biopsy"}
)

# Remove a relationship (soft delete)
client.unrelate(
    relationship_id="edge-uuid",
    actor="data-team",
    reason="Incorrectly linked"
)

# Query relationships
edges = client.relationships(
    entity_type="Subject", entity_id="subj-uuid",
    relationship="donated",
    direction="outbound"
)
```

#### ExternalID operations

```python
# Register an ExternalID
client.register_external_id(
    entity_type="Sample", entity_id="uuid",
    system="starlims", external_id="SL-123",
    actor="data-team"
)

# Correct an ExternalID (supersession)
client.correct_external_id(
    entity_type="Sample", entity_id="uuid",
    system="starlims",
    old_value="SL-123", new_value="SL-124",
    reason="Transcription error",
    actor="data-team"
)
```

#### Provenance operations

```python
# Full history for an entity
events = client.history("Sample", "uuid")
# Returns list[ProvenanceRecord] in chronological order

# Filtered history
events = client.history("Sample", "uuid",
    event_types=["EntityUpdated", "AvailabilityChanged"],
    since="2024-01-01T00:00:00Z"
)

# State reconstruction at a point in time
state = client.state_at("Sample", "uuid", timestamp="2024-06-01T00:00:00Z")
```

#### Schema introspection

```python
# List all entity types
entity_types = client.schema.entity_types()

# Describe an entity type (fields, validators, relationships)
descriptor = client.schema.describe("Sample")

# List installed reference loaders
loaders = client.schema.reference_loaders()

# Check deprecated fields
deprecated = client.schema.deprecated_fields("Sample")

# Check subtype hierarchy
subtypes = client.schema.subtypes("Sample")   # ["BrainSample", "CellLine"]
ancestors = client.schema.ancestors("BrainSample")  # ["Sample"]
```

---

### 4.3 REST API

The REST API is a FastAPI application. All endpoints call `HippoClient` directly — no
separate REST-layer business logic.

Base path: `/api/v1`

Auto-generated docs available at `/docs` (Swagger UI) and `/redoc`. OpenAPI JSON at
`/openapi.json`.

#### Entity endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/entities/{entity_type}` | Query entities (supports filter params, pagination) |
| `POST` | `/entities/{entity_type}` | Create or update an entity (upsert) |
| `GET` | `/entities/{entity_type}/{entity_id}` | Fetch entity by UUID |
| `GET` | `/entities/{entity_type}/{entity_id}/history` | Full provenance history |
| `POST` | `/entities/{entity_type}/{entity_id}/availability` | Set availability |
| `POST` | `/entities/{entity_type}/{entity_id}/supersede` | Supersede with another entity |
| `GET` | `/entities/{entity_type}/{entity_id}/relationships` | List relationships |

#### Search endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/search/{entity_type}` | Fuzzy search on a field (`?field=&q=&limit=&min_score=`) |

#### Relationship endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/relationships` | Create a relationship |
| `DELETE` | `/relationships/{relationship_id}` | Remove a relationship (soft delete) |

#### ExternalID endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/external-ids/{system}/{external_id}` | Lookup entity by ExternalID |
| `POST` | `/entities/{entity_type}/{entity_id}/external-ids` | Register ExternalID |
| `PUT` | `/entities/{entity_type}/{entity_id}/external-ids/{system}` | Correct ExternalID |

#### Ingestion endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/ingest/{entity_type}` | Batch ingest (JSON array body) |

#### Schema introspection endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/schema/entity-types` | List all entity types |
| `GET` | `/schema/entity-types/{entity_type}` | Describe an entity type |
| `GET` | `/schema/reference-loaders` | List installed reference loaders and versions |

#### System endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check — returns `{"status": "ok"}` |
| `GET` | `/status` | Adapter type, schema version, entity counts, plugin summary |

#### Standard request/response conventions

**Request headers:**
- `X-Hippo-Actor: <identity>` — actor for write operations (required on all writes; defaults
  to `"anonymous"` if absent in v0.1)
- `X-Hippo-Context: <JSON>` — provenance context JSON (optional)

**Response envelope (all responses):**
```json
{
  "data": { ... },        // null on error
  "error": null,          // null on success; see error format below
  "meta": {               // always present
    "schema_version": "1.1",
    "request_id": "uuid"
  }
}
```

**Error format:**
```json
{
  "data": null,
  "error": {
    "type": "ValidationError",
    "message": "Sample 'abc-123' failed validation",
    "detail": {
      "validator": "active_subject_check",
      "errors": ["Subject xyz is withdrawn"]
    }
  },
  "meta": { "schema_version": "1.1", "request_id": "uuid" }
}
```

HTTP status codes:
- `200 OK` — successful read
- `201 Created` — entity created
- `200 OK` — entity updated (not 204, always returns the entity)
- `404 Not Found` — `EntityNotFoundError`
- `422 Unprocessable Entity` — `ValidationError` (schema or rule)
- `409 Conflict` — `ConfigError` (e.g. adapter conflict)
- `500 Internal Server Error` — `AdapterError` (storage failure)

---

### 4.4 Pagination

**Opinionated decision:** Hippo uses **offset-based pagination** for v0.1. Cursor-based
pagination is deferred.

**Rationale:** Offset pagination is simpler to implement, universally understood, and
sufficient for the expected v0.1 query volumes. The main limitation (page drift when new
records are inserted during pagination) is acceptable for research workloads where callers
typically retrieve complete result sets rather than paginating live feeds.

#### SDK pagination

```python
# Automatic pagination: iterates all pages and yields individual entities
for sample in client.iter_query("Sample", tissue_type="brain"):
    process(sample)

# Manual pagination: caller controls page fetch
page = client.query("Sample", tissue_type="brain", limit=100, offset=0)
# page.items: list[dict]
# page.total: int (total matching entities, not just this page)
# page.limit: int
# page.offset: int
# page.has_more: bool
```

#### REST pagination

Query parameters: `?limit=<n>&offset=<n>` (default limit: 100, max: 1000)

Response includes pagination metadata in `meta`:

```json
{
  "data": [ ...entities... ],
  "error": null,
  "meta": {
    "schema_version": "1.1",
    "request_id": "uuid",
    "pagination": {
      "total": 4821,
      "limit": 100,
      "offset": 200,
      "has_more": true
    }
  }
}
```

---

### 4.5 `query_updated_since` — Polling Support

This method is designed for Cappella's `hippo_poll` trigger source and any other caller that
needs efficient change detection.

```python
recent = client.query_updated_since(
    entity_type="Sample",
    since="2024-01-01T00:00:00Z",
    limit=500,
    offset=0
)
```

**Implementation:** Uses the `entity_provenance_summary` view (see sec6 §6.6) to find
entities with `updated_at > since`, ordered by `updated_at` ascending (oldest first, so
callers can process in order and advance their watermark incrementally).

**REST endpoint:**

```
GET /entities/{entity_type}?updated_since=<ISO8601 timestamp>&limit=500
```

**Opinionated decision:** The `since` timestamp is based on Hippo's provenance `updated_at`
(server-side UTC), not any caller-supplied timestamp. This avoids clock skew issues between
Cappella and Hippo. Callers should persist the `updated_at` value of the last entity they
processed as their watermark for the next poll.

---

### 4.6 Open Questions

| Question | Priority | Notes |
|---|---|---|
| Cursor-based pagination | Medium | For large result sets and live-feed pagination. Defer to post-v0.1. |
| GraphQL transport | Low | Reserved in `hippo/graphql/`. Defer to post-v0.1. |
| Bulk relationship query | Medium | `client.relationships_bulk(entity_ids=[...])` — fetch relationships for many entities in one query. Useful for Cappella expand path engine. Omitted from v0.1 for simplicity; add when needed. |
| Rate limiting | Low | Out of scope for v0.1 (no auth layer). Add with auth in a future version. |

---
