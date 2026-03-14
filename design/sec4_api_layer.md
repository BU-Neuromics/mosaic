## 4. API Layer

**Document status:** Draft v0.1
**Depends on:** sec2_architecture.md, sec3_data_model.md, sec6_provenance.md
**Feeds into:** sec5_ingestion.md, sec7_nfr.md

---

### 4.1 Overview

Hippo exposes its functionality through two API surfaces:

1. **Python SDK (`HippoClient`)** — the primary interface; all logic lives here
2. **REST API** — a thin FastAPI transport layer wrapping the SDK

Both surfaces expose identical semantics. The REST API is an optional deployment concern —
single-user local deployments use the SDK directly. All examples in this section show both.

---

### 4.2 HippoClient Public Interface

`HippoClient` is the single entry point to all SDK functionality. It is instantiated with a
`HippoConfig` and exposes the full Hippo surface area.

```python
from hippo import HippoClient, HippoConfig

client = HippoClient(HippoConfig.from_file("hippo.yaml"))
```

#### Entity operations

```python
# Create or update a single entity
client.put(
    entity_type="Sample",
    entity={"tissue_type": "brain", "collection_date": "2024-03-01"},
    actor="admin",
    provenance_context={"source": "manual"}
)
# → ProvenanceRecord

# Get a single entity by ID
client.get("Sample", entity_id)
# → dict (entity fields + system fields created_at, updated_at, schema_version, __type__)

# Atomic upsert by external ID
client.upsert(
    entity_type="Sample",
    external_system="starlims",
    external_id="STARLIMS:12345",
    fields={...},
    actor="cappella",
)
# → UpsertResult(action="created"|"updated"|"unchanged", entity_id=str)

# Availability operations
client.set_availability("Sample", entity_id, available=False,
                        reason="withdrawn", actor="admin")
client.supersede("Sample", old_id="abc", new_id="def",
                 reason="corrected annotation", actor="admin")
```

#### Query operations

```python
# Filter query — returns available entities by default
client.query(
    "Sample",
    filters=[
        Filter("tissue_type", "eq", "brain"),
        Filter("collection_date", "gte", "2024-01-01"),
    ],
    include_unavailable=False,   # default
    exact_type=False,            # default: include subtypes
    page=1,
    page_size=100,
)
# → Page(items=[dict, ...], total=int, page=int, page_size=int, pages=int)

# Get by external ID
client.get_by_external_id("Sample", system="starlims", external_id="STARLIMS:12345")
# → dict | None

# Graph traversal — follow a named relationship
client.traverse("Sample", entity_id, relationship="donated", direction="from")
# → list[dict] — entities on the other end of the relationship

# Point-in-time snapshot
client.entity_at("Sample", entity_id, at=datetime(...))
# → dict
```

#### Search operations

```python
# Fuzzy search on a searchable field
client.search("AnatomyTerm", field="preferred_label", query="prefrontal cortex",
              limit=5, min_score=0.5)
# → list[ScoredMatch]
```

#### Relationship operations

```python
client.add_relationship(
    relationship="donated",
    from_type="Subject", from_id="...",
    to_type="Sample",   to_id="...",
    actor="admin",
    properties={"method": "surgical biopsy"}
)

client.remove_relationship(relationship_id="...", actor="admin", reason="data error")
```

#### Provenance operations

```python
client.history("Sample", entity_id)
# → list[ProvenanceEvent]

client.events_since("Sample", since=datetime(...), event_types=None)
# → list[ProvenanceEvent]

client.events_by_context(key="sync_run_id", value="uuid")
# → list[ProvenanceEvent]
```

#### Schema operations

```python
client.schema.entity_types()                    # → list[str]
client.schema.fields("Sample")                  # → dict[str, FieldDef]
client.schema.relationships()                   # → list[RelationshipDef]
client.schema.is_subtype_of("BrainSample", "Sample")  # → bool
client.schema.deprecated_fields("Sample")       # → list[str]
```

---

### 4.3 Filter API

Filters are composable predicates on entity fields. The `Filter` type:

```python
@dataclass
class Filter:
    field: str
    operator: str   # see table below
    value: Any
```

Supported operators:

| Operator | Meaning | Field types |
|---|---|---|
| `eq` | Equal | all |
| `neq` | Not equal | all |
| `gt`, `gte`, `lt`, `lte` | Comparison | int, float, date, datetime |
| `in` | Value in list | all |
| `not_in` | Value not in list | all |
| `contains` | Substring match | string |
| `starts_with` | Prefix match | string |
| `is_null` | Field is null | all |
| `is_not_null` | Field is not null | all |

Multiple filters are ANDed together. OR composition is not supported in v0.1 — complex
boolean queries should use the REST search endpoint with a CEL expression (future).

**Filtering on subtype fields:** When querying a parent type, filters on child-only fields
require `exact_type=True` or explicit subtype declaration. Filtering on `brain_region`
(a `BrainSample`-only field) when querying `Sample` without `exact_type` raises a
`QueryError` identifying the ambiguity.

---

### 4.4 Pagination

All list-returning endpoints and SDK methods are paginated. There are no unbounded list
operations in v0.1.

**Pagination model:** Offset-based pagination via `page` (1-indexed) and `page_size`
(default 100, max 1000).

```python
page = client.query("Sample", filters=[...], page=1, page_size=100)
page.items       # list[dict]
page.total       # total matching records
page.page        # current page number
page.page_size   # records per page
page.pages       # total number of pages
```

**Opinionated decision:** Cursor-based pagination is more correct for large mutable datasets
but significantly more complex to implement and consume. Offset pagination is sufficient for
v0.1 workloads (research labs, not web-scale traffic). Cursor pagination is the natural
upgrade path if needed.

**`events_since` and `history` pagination:** Provenance queries also return `Page` objects.
Default `page_size` for provenance queries is 500.

---

### 4.5 REST API Design

The REST API is a FastAPI application. All endpoints return JSON. All writes require an
`X-Hippo-Actor` header (defaulting to `"anonymous"` in v0.1 when auth is disabled).

#### Entity endpoints

```
GET    /entities/{entity_type}
       ?filter=<field:op:value>  (repeatable)
       &include_unavailable=false
       &exact_type=false
       &page=1&page_size=100
       → Page<EntityResponse>

POST   /entities/{entity_type}
       Body: {fields: {...}, provenance_context: {...}}
       → EntityResponse

GET    /entities/{entity_type}/{id}
       → EntityResponse

PATCH  /entities/{entity_type}/{id}
       Body: {fields: {...}, provenance_context: {...}}
       → EntityResponse

POST   /entities/{entity_type}/{id}/availability
       Body: {available: bool, reason: str}
       → EntityResponse

POST   /entities/{entity_type}/{id}/supersede
       Body: {new_id: str, reason: str}
       → EntityResponse
```

#### Query and search endpoints

```
GET    /entities/{entity_type}/by-external-id
       ?system=<s>&id=<v>
       → EntityResponse | 404

POST   /entities/{entity_type}/upsert
       Body: {external_system: str, external_id: str, fields: {...}}
       → UpsertResponse

GET    /entities/{entity_type}/search
       ?field=<f>&q=<query>&limit=10&min_score=0.0
       → list[ScoredMatchResponse]

GET    /entities/{entity_type}/{id}/traverse
       ?relationship=<r>&direction=from|to&page=1&page_size=100
       → Page<EntityResponse>

GET    /entities/{entity_type}/{id}/at
       ?t=<ISO-8601>
       → EntityResponse
```

#### Relationship endpoints

```
GET    /relationships?from_type=<t>&from_id=<id>&relationship=<r>
       → Page<RelationshipResponse>

POST   /relationships
       Body: {relationship: str, from_type, from_id, to_type, to_id, properties: {...}}
       → RelationshipResponse

DELETE /relationships/{id}
       Body: {reason: str}
       → RelationshipResponse (status: removed)
```

#### Provenance endpoints

```
GET    /provenance/{entity_type}/{id}
       ?page=1&page_size=500
       → Page<ProvenanceEventResponse>

GET    /provenance/{entity_type}/{id}/at
       ?t=<ISO-8601>
       → EntityResponse

GET    /provenance/events
       ?since=<ISO>&actor=<s>&event_type=<t>&context_key=<k>&context_value=<v>
       &page=1&page_size=500
       → Page<ProvenanceEventResponse>
```

#### Ingestion endpoints

```
POST   /ingest/{entity_type}
       Body: multipart/form-data, file + optional mapping JSON
       → IngestResult

POST   /ingest/{entity_type}/batch
       Body: [HippoRecord, ...]
       → IngestResult
```

#### Schema endpoints

```
GET    /schema
       → {entity_types: [...], relationships: [...], version: str}

GET    /schema/{entity_type}
       → {fields: {...}, base: str|null, relationships: [...]}
```

#### Response shapes

```python
# EntityResponse
{
    "id": "uuid",
    "entity_type": "BrainSample",
    "__type__": "BrainSample",        # concrete type
    "is_available": true,
    "created_at": "2024-03-01T...",
    "updated_at": "2024-03-15T...",
    "schema_version": "1.0",
    # ... user-defined fields ...
}

# UpsertResponse
{
    "action": "created" | "updated" | "unchanged",
    "entity_id": "uuid",
    "entity_type": "Sample"
}

# ScoredMatchResponse
{
    "entity_id": "uuid",
    "entity_type": "AnatomyTerm",
    "field": "preferred_label",
    "value": "dorsolateral prefrontal cortex",
    "score": 0.94,
    "match_mode": "fts"
}
```

#### Error responses

All errors follow the same JSON envelope (see sec2 §2.11):

```json
{
    "error": "EntityNotFoundError",
    "message": "Sample 'abc-123' not found",
    "detail": {}
}
```

HTTP status code mapping:

| Error type | HTTP status |
|---|---|
| `EntityNotFoundError` | 404 |
| `SchemaValidationError` | 422 |
| `RuleValidationError` | 422 |
| `IngestError` | 422 |
| `SearchCapabilityError` | 422 |
| `AdapterError` | 500 |
| `ConfigError` | 500 |

---

### 4.6 Filter Encoding in REST

Filters are encoded as repeated `filter` query parameters using the format
`field:operator:value`:

```
GET /entities/Sample?filter=tissue_type:eq:brain&filter=collection_date:gte:2024-01-01
```

For `in` / `not_in` operators, values are comma-separated:

```
GET /entities/Sample?filter=tissue_type:in:brain,cortex,hippocampus
```

---

### 4.7 OpenAPI and Client Generation

The REST API automatically generates an OpenAPI 3.1 schema at `/openapi.json` and a
Swagger UI at `/docs`. The OpenAPI schema is the authoritative interface contract for
REST clients.

**Opinionated decision:** Hippo does not ship language-specific client SDKs in v0.1.
The Python SDK is the primary client. REST consumers can generate typed clients from the
OpenAPI schema using standard tools (openapi-generator, etc.).

---

### 4.8 Open Questions

| Question | Priority | Notes |
|---|---|---|
| Cursor-based pagination | Low | Offset pagination sufficient for v0.1. Upgrade path if high-throughput streaming queries become a requirement. |
| OR filter composition | Low | AND-only filters sufficient for v0.1. A CEL-based filter expression endpoint is the natural extension (future). |
| Bulk delete / availability change | Medium | `POST /entities/{type}/bulk-availability` for marking many entities unavailable at once. Needed for large dataset archival. Deferred from v0.1. |

---
