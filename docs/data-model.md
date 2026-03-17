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
| `created_at` | datetime | Timestamp of entity creation (UTC) |
| `updated_at` | datetime | Timestamp of most recent change (UTC) |
| `version` | int | Monotonically increasing version number |

The `created_at`, `updated_at`, and `version` fields are stored directly on entities. The design spec describes these as computed from the provenance log at read time, but the current implementation stores them directly on the entity record for performance.

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
samples = client.query("Sample", filters=[...])
```

To include unavailable entities, use the `include_archived` parameter where supported:

```python
# Include archived entities
entity = client.get_by_external_id("EXT-123", include_archived=True)
```

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

External IDs are immutable once written. To "correct" an external ID, you supersede the old one with a new one:

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

## Supersession

Supersession replaces one entity with another, commonly used for corrections or updates:

```python
# Current implementation: supersedes external IDs only
new_record = client.supersede(
    entity_id="abc-123",
    old_external_id="OLD-ID",
    new_external_id="NEW-ID"
)
```

**Gap:** The design spec describes entity-level supersession (replacing one entity UUID with another), but the current implementation only supports external ID supersession. Entity-level supersession would:
1. Mark the old entity as unavailable
2. Create a `superseded_by` relationship edge
3. Record the reason in provenance

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
# - operation_type: CREATE, UPDATE, or SOFT_DELETE
# - timestamp: When the operation occurred
# - user_id: Who performed the operation
# - previous_state_hash: Hash of previous state
# - state_snapshot: Entity state at that point
```

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
samples = client.query(
    entity_type="Sample",
    filters=[
        {"field": "tissue_type", "operator": "eq", "value": "brain"},
        {"field": "passage", "operator": "gte", "value": 5}
    ]
)
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
samples = client.query(
    entity_type="Sample",
    limit=50,
    offset=100  # Skip first 100 results
)
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

This section documents the core types used in the Hippo SDK.

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

A group of conditions combined with a logical operator.

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

Paginated query result with metadata.

```python
from hippo.core.types import PaginatedResult

result = PaginatedResult(
    items=[...],
    total=150,
    page=2,
    page_size=50
)
```

**Gap:** The `query()` method currently returns a plain list, not `PaginatedResult`. This type is defined but not used in the client.

### ScoredMatch

Search result with relevance scoring.

```python
from hippo.core.types import ScoredMatch

match = ScoredMatch(
    score=0.95,
    match_data={"id": "abc-123", "data": {...}},
    matched_fields=["preferred_label", "description"]
)
```

### WriteOperation

Represents a write operation for validation.

```python
from hippo.core.types import WriteOperation

operation = WriteOperation(
    success=True,
    operation="insert",  # or "update", "delete"
    entity_type="Sample",
    entity_id="abc-123",
    metadata={}
)
```

### ValidationError

A single validation failure.

```python
from hippo.core.types import ValidationError

error = ValidationError(
    field="external_id",
    message="external_id is required"
)
```

### ValidationResult

Result of validation pipeline execution.

```python
from hippo.core.types import ValidationResult

result = ValidationResult(
    valid=False,
    errors=[
        ValidationError(field="external_id", message="required")
    ]
)

# Convenience property
if result.is_valid:
    print("Validation passed")
```

### ProvenanceRecord

A single record in the provenance log.

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

Status of a bulk ingestion operation.

```python
from hippo.core.types import IngestStatus

# SUCCESS, PARTIAL, FAILED
```

### IngestResult

Result of a bulk ingestion operation.

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

### 1. Entity-Level Supersession

- **Design:** `client.supersede(entity_type, old_id, new_id, actor, reason)` replaces an entire entity with another
- **Implementation:** `client.supersede(entity_id, old_external_id, new_external_id)` only replaces external IDs

### 2. Provenance-Computed Temporal Fields

- **Design:** `created_at`, `updated_at`, `schema_version` are computed from the provenance log at read time
- **Implementation:** These fields are stored directly on the entity record in storage

### 3. Soft Delete Implementation

- **Design:** Delete operations set `is_available = false` via availability transitions
- **Implementation:** The `delete()` method calls `storage.delete()` directly; soft delete behavior depends on the storage adapter implementation

### 4. PaginatedResult Not Used

- **Design:** Query methods return `PaginatedResult` objects with pagination metadata
- **Implementation:** `client.query()` returns a plain `list[dict]`; `PaginatedResult` type is defined but unused

### 5. Relationship Properties

- **Design:** Relationships can carry typed properties declared in schema
- **Implementation:** The `RelationshipManager` exists but relationship properties are not fully implemented

### 6. Schema-Declared Search Modes

- **Design:** Schema declares `search: fts`, `search: embedding`, or `search: synonym`
- **Implementation:** FTS is implemented; embedding and synonym search are adapter-dependent

---

## See Also

- [Design Spec: Data Model](../design/sec3_data_model.md) — Full engineering specification
- [Design Spec: Architecture](../design/sec2_architecture.md) — SDK-first architecture
- [Design Spec: Provenance](../design/sec6_provenance.md) — Provenance event model
- [API Reference](./api-reference.md) — REST API endpoints
- [CLI Reference](./cli-reference.md) — Command-line tools
