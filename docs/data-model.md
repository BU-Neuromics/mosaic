# Hippo Data Model

This document describes Hippo's data model for users of the SDK. For the full engineering specification, see [Data Model design spec](../design/sec3_data_model.md).

---

## Core Concepts

### Entities

An **entity** is a typed data object in Hippo. Every entity has:

- A unique internal identifier (UUID)
- An entity type (e.g., `Sample`, `Subject`, `Datafile`)
- User-defined fields as declared in the schema
- System fields managed automatically by Hippo

Entity types and their fields are defined in the schema configuration (YAML or JSON), not hardcoded in the SDK.

### System Fields

Every entity carries the following read-only system fields:

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Unique identifier, generated on creation |
| `is_available` | bool | Controls visibility in default queries |
| `superseded_by` | UUID (nullable) | ID of the replacement entity if this entity has been superseded; `None` otherwise |
| `created_at` | datetime | Timestamp of entity creation (UTC), derived from the provenance log |
| `updated_at` | datetime | Timestamp of most recent change (UTC), derived from the provenance log |
| `schema_version` | string | Schema config version at most recent change, derived from the provenance log |

`superseded_by` is set atomically by `client.supersede_entity()` alongside the availability change. `client.get()` returns it on all entities; it is `None` when not superseded. The authoritative record of the supersession is the `EntitySuperseded` provenance event — the column is a fast-read cache.

The `created_at`, `updated_at`, and `schema_version` fields are derived at read time from the provenance log. The current implementation caches `created_at` and `updated_at` directly on the entity record for performance, but the provenance log is authoritative — `client.get()` reads from provenance when available and falls back to the cached values.

---

## Availability Semantics

Hippo uses **soft deletes** — there are no hard deletes. Every entity carries an `is_available` boolean field:

- `is_available = true`: Entity appears in default query results
- `is_available = false`: Entity is hidden from default queries but retained in storage

When an entity becomes unavailable, the **reason** is recorded in the provenance event (e.g., `archived`, `deleted`, `superseded`), not on the entity itself.

### Default Query Behavior

All query operations return only available entities by default:

```python
# Returns only available samples
result = client.query("Sample", filters=[...])
```

To include unavailable entities, use the `include_archived` parameter where supported:

```python
# Include archived entities
entity = client.get_by_external_id("EXT-123", include_archived=True)
```

---

## Entity Namespaces (FQNs)

Entity type strings in Hippo are optionally namespace-qualified. Namespaces allow multiple subsystems to define their own `Sample` or `Subject` types without collision.

### Namespace Syntax

- **Root namespace** (no prefix): `"Sample"`, `"Donor"` — entity types declared without a namespace key
- **Named namespace**: `"tissue.Sample"`, `"omics.Datafile"` — the prefix before the dot is the namespace name
- **Explicit root prefix**: `"root.Donor"` is equivalent to `"Donor"` — normalized at schema load time

### Using FQNs in SDK Calls

FQNs are valid wherever an `entity_type` string is accepted:

```python
# Root namespace (no prefix needed)
client.put("Sample", data={...})
client.get("Donor", entity_id="abc-123")
client.query("Subject", filters=[...])

# Named namespace
client.put("tissue.Sample", data={...})
client.get("tissue.Sample", entity_id="abc-123")
client.query("tissue.Sample", filters=[...])
```

### Declaring Namespaces in Schema Config

Add a `namespace:` key at the top of a schema file to scope all its entity types:

```yaml
# schemas/tissue.yaml
namespace: tissue
entities:
  Sample:
    fields:
      donor_id: {type: string, references: {entity_type: Donor}}        # root Donor
      parent_id: {type: string, references: {entity_type: tissue.Sample}} # self-ref
```

Schemas without a `namespace:` key contribute to the root namespace. Multiple files may share the same namespace — their entity lists are merged at load time. Cross-namespace references use FQNs in `references.entity_type`.

Existing schemas with no `namespace:` key are unaffected. All unqualified entity type strings continue to resolve to the root namespace; no data migration is required.

---

## External IDs

External IDs connect Hippo entities to identifiers from upstream systems (LIMS, lab databases, etc.).

### Registering External IDs

```python
# Register an external ID for an entity
record = client.register_external_id(
    entity_id="abc-123",
    external_id="SAMPLE-001"
)
```

### Lookup by External ID

```python
# Find an entity by its external ID
entity = client.get_by_external_id("SAMPLE-001")

# Include archived entities in search
entity = client.get_by_external_id("SAMPLE-001", include_archived=True)
```

### Listing External IDs

```python
# List all external IDs for an entity
external_ids = client.list_external_ids(entity_id="abc-123")

# Include superseded (replaced) IDs
external_ids = client.list_external_ids(entity_id="abc-123", include_superseded=True)
```

### External ID Immutability

External IDs are immutable once written. To "correct" an external ID, supersede the old one with a new one:

```python
# Replace an external ID with a corrected value
new_record = client.supersede(
    entity_id="abc-123",
    old_external_id="SAMPLE-001-INCORRECT",
    new_external_id="SAMPLE-001-CORRECTED"
)
```

This creates a new active external ID record and marks the old one as superseded. Both records are retained for audit purposes.

---

## Relationships

Relationships are typed, directional edges between entities. They are declared in the schema:

```yaml
relationships:
  - name: derived_from
    from: Sample
    to: Sample
    cardinality: many-to-many
    properties:
      method: {type: string}
```

Supported cardinalities:
- `one-to-many`: One entity relates to many (e.g., Subject → Samples)
- `many-to-one`: Many entities relate to one (e.g., Sample → Subject)
- `many-to-many`: Bidirectional many-to-many (e.g., Sample ↔ Sample via derived_from)

### Graph Traversal

Use the `expand` parameter to fetch related entities in a single query:

```python
# Fetch a sample with its subject
sample = client.get(
    entity_type="Sample",
    entity_id="abc-123",
    expand="subject"
)
```

The `expand` parameter supports nested paths:

```python
# Fetch sample → subject → diagnosis
sample = client.get(
    entity_type="Sample",
    entity_id="abc-123",
    expand="subject.diagnosis"
)
```

---

## Entity Supersession

Entity supersession replaces one entity with another. This is used when an entity needs to be corrected or updated in a way that preserves the full audit trail of the old record.

### supersede_entity()

`client.supersede_entity()` is an atomic operation that:

1. Marks the old entity as unavailable (`is_available = false`)
2. Sets `superseded_by` on the old entity to the new entity's UUID
3. Writes an `EntitySuperseded` provenance event on the old entity
4. Creates a `superseded_by` relationship edge from old to new
5. Writes an `EntityUpdated` provenance event on the new entity

All five writes succeed together or roll back entirely on failure.

```python
client.supersede_entity(
    entity_id="abc-123",
    replacement_id="def-456",
    actor="pipeline-run-789",
    reason="Corrected tissue region annotation"
)
```

Both entities are retained — there are no hard deletes. The old entity remains queryable via `client.get()` (which returns superseded entities) and `client.history()`.

### Raises

- `EntityNotFoundError` — if either `entity_id` or `replacement_id` does not exist
- `EntityAlreadySupersededError` — if `entity_id` is already superseded

---

## Provenance and History

Every change to an entity is recorded in the provenance log.

### Viewing History

```python
# Get full change history for an entity
history = client.history(entity_id="abc-123")

# Returns list of records in chronological order (oldest first)
# Each record contains:
# - operation_id: Unique identifier
# - entity_id: The entity ID
# - entity_type: The entity type
# - operation_type: CREATE, UPDATE, SOFT_DELETE, EntitySuperseded, etc.
# - timestamp: When the operation occurred
# - user_id: Who performed the operation
# - previous_state_hash: Hash of previous state
# - state_snapshot: Entity state at that point
```

`client.history()` accepts superseded (unavailable) entity IDs.

### Querying Historical State

```python
# Get entity state at a specific point in time
state = client.state_at(
    entity_id="abc-123",
    timestamp="2024-01-15T10:30:00+00:00"
)
```

This returns the entity's data as it existed at the specified timestamp.

---

## Query API

### Basic Queries

```python
# Query entities with filters
result = client.query(
    entity_type="Sample",
    filters=[
        {"field": "tissue_type", "operator": "eq", "value": "brain"},
        {"field": "passage", "operator": "gte", "value": 5}
    ]
)

# result is a PaginatedResult
for item in result.items:
    print(item["id"], item["data"])

print(f"Showing {len(result.items)} of {result.total} total")
```

### Filter Operators

| Operator | Description |
|---|---|
| `eq` | Equal to |
| `ne` | Not equal to |
| `gt` | Greater than |
| `gte` | Greater than or equal |
| `lt` | Less than |
| `lte` | Less than or equal |
| `in` | In list |
| `not_in` | Not in list |
| `contains` | String contains |
| `starts_with` | String starts with |
| `ends_with` | String ends with |
| `is_null` | Field is null |
| `is_not_null` | Field is not null |

### Pagination

```python
# Query with pagination
result = client.query(
    entity_type="Sample",
    limit=50,
    offset=100  # Skip first 100 results
)

# result.total is the count before limit/offset
print(f"Page: {len(result.items)} items, {result.total} total")
```

### Full-Text Search

```python
# Search using FTS5
results = client.search(
    entity_type="Sample",
    query="brain AND cortex",
    limit=20
)
```

---

## Write Operations

### Create

```python
# Create a new entity
sample = client.create(
    entity_type="Sample",
    data={
        "external_id": "SAMPLE-001",
        "tissue_type": "brain",
        "tissue_region": "frontal cortex"
    }
)
```

### Update

```python
# Update an existing entity
sample = client.update(
    entity_type="Sample",
    entity_id="abc-123",
    data={
        "external_id": "SAMPLE-001",
        "tissue_type": "brain",
        "tissue_region": "temporal cortex"  # Corrected value
    }
)
```

### Upsert

```python
# Create or update by ID
sample = client.put(
    entity_type="Sample",
    entity_id="abc-123",  # If provided and exists → update; if not provided → create
    data={...}
)
```

### Delete

```python
# Delete an entity (soft delete - sets is_available=false)
result = client.delete(
    entity_type="Sample",
    entity_id="abc-123"
)
```

**Gap:** The design spec describes soft delete via availability transitions, but the current implementation calls `storage.delete()` directly. The SQLite adapter may implement soft delete internally.

---

## SDK Types Reference

This section documents the user-facing types exported from `hippo.core.types`.

### FilterCondition

A single filter condition for queries.

```python
from hippo.core.types import FilterCondition, FilterOperator

condition = FilterCondition(
    field="tissue_type",
    operator=FilterOperator.EQ,
    value="brain"
)
```

### FilterGroup

A group of conditions combined with a logical operator. Supports nested groups via the `groups` field.

```python
from hippo.core.types import FilterGroup, FilterCondition, FilterOperator, LogicalOperator

group = FilterGroup(
    conditions=[
        FilterCondition(field="tissue_type", operator=FilterOperator.EQ, value="brain"),
        FilterCondition(field="passage", operator=FilterOperator.GTE, value=5)
    ],
    logical_operator=LogicalOperator.AND
)
```

### Filter

Top-level filter container supporting nested groups.

```python
from hippo.core.types import Filter, FilterGroup

filter_obj = Filter(root=FilterGroup(conditions=[...]))
```

### FilterOperator

Enum of supported comparison operators.

```python
from hippo.core.types import FilterOperator

# EQ, NE, GT, GTE, LT, LTE, IN, NOT_IN, CONTAINS, STARTS_WITH, ENDS_WITH, IS_NULL, IS_NOT_NULL
```

### LogicalOperator

Enum for combining filter conditions.

```python
from hippo.core.types import LogicalOperator

# AND, OR
```

### PaginatedResult

Paginated query result returned by `client.query()`.

| Field | Type | Description |
|---|---|---|
| `items` | `list[Any]` | The entities on this page |
| `total` | `int` | Total matching entities across all pages (ignoring `limit`/`offset`) |
| `limit` | `int` | Maximum items per page; `0` means no limit |
| `offset` | `int` | Number of items skipped |

```python
from hippo.core.types import PaginatedResult

result = client.query("Sample", limit=50, offset=0)

# result.items — list of entity dicts on this page
# result.total — count before limit/offset was applied
# result.limit — the limit that was passed (50)
# result.offset — the offset that was passed (0)
```

### ScoredMatch

Search result with relevance scoring. Returned by search operations.

| Field | Type | Description |
|---|---|---|
| `score` | `float` | Relevance score (higher is more relevant) |
| `match_data` | `dict[str, Any]` | The matched entity data |
| `matched_fields` | `list[str]` | Fields that matched the query |

```python
from hippo.core.types import ScoredMatch

match = ScoredMatch(
    score=0.95,
    match_data={"id": "abc-123", "data": {...}},
    matched_fields=["preferred_label", "description"]
)
```

### WriteOperation

Represents a write operation result.

| Field | Type | Description |
|---|---|---|
| `success` | `bool` | Whether the operation succeeded |
| `operation` | `str` | Type of operation: `"insert"`, `"update"`, or `"delete"` |
| `entity_type` | `str` | The entity type affected |
| `entity_id` | `str \| None` | ID of the affected entity |
| `metadata` | `dict[str, Any]` | Additional operation metadata |

```python
from hippo.core.types import WriteOperation

operation = WriteOperation(
    success=True,
    operation="insert",
    entity_type="Sample",
    entity_id="abc-123",
    metadata={}
)
```

### ProvenanceRecord

A single record in the provenance log.

| Field | Type | Description |
|---|---|---|
| `source` | `str` | Origin system or entity |
| `timestamp` | `datetime` | When the operation occurred |
| `operation` | `str` | Type of operation: `"create"`, `"update"`, `"read"`, `"delete"` |
| `entity_type` | `str \| None` | Type of entity affected |
| `entity_id` | `str \| None` | ID of the entity |
| `user_context` | `str \| None` | User or system context that initiated the operation |
| `payload` | `dict[str, Any]` | Complete entity state as JSON |

```python
from hippo.core.types import ProvenanceRecord
from datetime import datetime

record = ProvenanceRecord(
    source="hippo-sdk",
    timestamp=datetime.now(),
    operation="create",
    entity_type="Sample",
    entity_id="abc-123",
    user_context="pipeline-run-456",
    payload={"external_id": "SAMPLE-001", ...}
)
```

### IngestStatus

Status enum for bulk ingestion operations.

```python
from hippo.core.types import IngestStatus

# IngestStatus.SUCCESS  — all items processed successfully
# IngestStatus.PARTIAL  — some items failed
# IngestStatus.FAILED   — all items failed
```

### IngestResult

Result of a bulk ingestion operation.

| Field | Type | Description |
|---|---|---|
| `status` | `IngestStatus` | Overall ingestion status |
| `total_processed` | `int` | Total items processed |
| `successful` | `int` | Number of successfully processed items |
| `failed` | `int` | Number of failed items |
| `errors` | `list[dict[str, Any]]` | Error details for failed items |
| `metadata` | `dict[str, Any]` | Additional result metadata |

```python
from hippo.core.types import IngestResult, IngestStatus

result = IngestResult(
    status=IngestStatus.PARTIAL,
    total_processed=100,
    successful=95,
    failed=5,
    errors=[
        {"index": 5, "message": "Validation failed for field X"}
    ],
    metadata={}
)
```

---

## Gaps Between Design and Implementation

This section documents known gaps between the design specification and current implementation.

### 1. Provenance-Computed Temporal Fields

- **Design:** `created_at`, `updated_at`, `schema_version` are computed exclusively from the provenance log at read time; never stored on the entity record
- **Implementation:** `created_at` and `updated_at` are cached directly on the entity row in storage. `client.get()` reads provenance timestamps when available and falls back to the cached values. `schema_version` is not yet derived from provenance.

### 2. Soft Delete Implementation

- **Design:** Delete operations set `is_available = false` via availability transitions
- **Implementation:** The `delete()` method calls `storage.delete()` directly; soft delete behavior depends on the storage adapter implementation

### 3. Relationship Properties

- **Design:** Relationships can carry typed properties declared in schema
- **Implementation:** The `RelationshipManager` exists but relationship properties are not fully implemented

### 4. Schema-Declared Search Modes

- **Design:** Schema declares `search: fts`, `search: embedding`, or `search: synonym`
- **Implementation:** FTS is implemented; embedding and synonym search are adapter-dependent

---

## See Also

- [Design Spec: Data Model](../design/sec3_data_model.md) — Full engineering specification
- [Design Spec: Architecture](../design/sec2_architecture.md) — SDK-first architecture
- [Design Spec: Provenance](../design/sec6_provenance.md) — Provenance event model
- [API Reference](./api-reference.md) — REST API endpoints
- [CLI Reference](./cli-reference.md) — Command-line tools
