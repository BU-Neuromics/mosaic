# `Process` Class — Composite Activity Grouping

## Why

Hippo's atomic audit log (`ProvenanceRecord`) is 1:1 with entity — one record per operation per entity. Real-world activities — reference-data loads, schema migrations, Cappella pipelines, batch upserts — touch many entities under one logical execution. Without a first-class construct that names the enclosing activity, these records can't be correlated at schema level; callers would have to stuff correlation keys into the unstructured `context` blob, a loose convention that fails the agent-readability bar.

sec9 §9.5 introduces `Process` as a first-class LinkML class in `hippo_core`. Atomic `ProvenanceRecord` entries carry a `process_id` FK to a `Process`; the `Process` itself is a `prov:Activity` with start/end times, operation kind, actor, and (optionally) a parent process for composition. Callers extend `Process` via `is_a: Process` for domain-specific attributes (pipeline parameters, inputs/outputs, runtime metadata).

This change introduces `Process` as a standalone table; consumers — `ProvenanceRecord.process_id` and the computed temporal fields — land in Wave 2 changes that build on this foundation.

This is Wave 1 #4 per sec9 §9.12. It depends on `id-registry-and-uuid-strategy` (needs UUID + registry infrastructure so `Process` entities participate in polymorphic resolution like any other entity) and blocks `provenance-as-linkml-class`.

## What Changes

### `Process` class in `hippo_core.yaml`

- `Process is_a: Entity` (inherits `id`, `is_available`).
- `class_uri: prov:Activity` (PROV-O alignment, shared with `ProvenanceRecord` at the composite scale).
- Minimum slot inventory (per sec9 §9.5):

| Slot | Type | Required | Semantics |
|---|---|---|---|
| `parent_process_id` | string (UUID) | no | Self-reference for process composition. Processes form a tree. |
| `operation_kind` | string | yes | Caller-defined categorization (`reference_data_installed`, `pipeline_run`, `schema_migration`, `manual_edit`, …). |
| `started_at` | datetime | yes | UTC wall-clock time at which the process began. |
| `ended_at` | datetime | no | UTC wall-clock time at which the process completed. Null while running or after failure without completion. |
| `actor_id` | string (UUID) | yes | Entity responsible for initiating the process. Resolves via the identity model. |

Richer attributes (inputs, outputs, lifecycle state, runtime metadata) are caller concerns — added via `is_a: Process` subclasses.

### DDL generation for `Process`

- The existing DDL generator now exercises one `hippo_core` class (first time an internal class goes through the DDL path); treat this change as the canary for `provenance-as-linkml-class` and subsequent Wave 2 work.
- Table `process` with columns matching the slot set.
- Primary key: `id` (UUID, per `Entity`).
- Indexes on `parent_process_id`, `operation_kind`, `started_at` (supports the expected query patterns).
- Foreign key to `_entity_registry` on `id` (via the adapter's usual mechanism).

### `is_a: Process` user-schema subclasses

Callers declare their own composite-activity classes via `is_a: Process`. Example (conceptual, not shipped):

```yaml
# cappella schema fragment
classes:
  PipelineRun:
    is_a: Process
    class_uri: prov:Activity
    attributes:
      pipeline_name:
        range: string
        required: true
      parameters:
        range: string          # JSON
      inputs:
        range: Entity          # multivalued FK
        multivalued: true
```

The DDL pipeline produces a `pipeline_run` table that inherits the `Process` columns (how inheritance materializes — single-table, joined, concrete — follows whatever strategy the DDL generator already uses for `is_a`, consistent with sec3b).

### Lifecycle provenance for `Process` entities

- Process creation emits a `create` provenance record for the `Process.id` (which is an `Entity.id`).
- State updates (start → end) emit `update` records. The transition from "running" to "completed" is modeled by setting `ended_at` and emitting an `update`, not a special operation.
- Archival uses the standard `availability_change` path.
- This works today because `Process is_a Entity` and `ProvenanceRecord` already accepts any `Entity.id` as `entity_id`. No special-casing.

### SDK surface

- `HippoClient.create("Process", {...})` and `HippoClient.get(uuid)` work as for any entity.
- No new public API methods required. Processes are entities.
- Callers track process lifecycle explicitly: create with `started_at`, update with `ended_at` when done.

### Tests

- Create a `Process` instance; verify DDL, registry row, and provenance create-event.
- Update a `Process` (set `ended_at`); verify the update is recorded and `is_available` stays true.
- Parent/child `Process` tree: create parent, create child with `parent_process_id`, verify the self-referential FK works.
- Subclass via `is_a: Process`: create a `PipelineRun` (in test fixtures), verify it inherits `Process` slots and gets its own table with the extra columns.
- Query: `SELECT * FROM process WHERE parent_process_id = ?` for tree traversal.

## Capabilities

### New Capabilities

- `process-class` — `Process` declared in `hippo_core`, DDL-generated, queryable.
- `composite-activity-modeling` — caller-extensible composite activity class with PROV-O alignment.

### Modified Capabilities

- `hippo-data-model` — `Process` joins `Entity` and the forthcoming `ProvenanceRecord` as a first-class class.
- `hippo-core-schema` (new in the preceding change) — gains the `Process` class.

## Open Questions

- **Inheritance strategy for `is_a: Process`.** Single-table vs. joined-table vs. concrete-table is dictated by the DDL generator's existing `is_a` handling per sec3b. This change adopts whatever is already in place; if sec3b's revision later changes the strategy, this change does not re-litigate.
- **Indexing `parent_process_id`.** Index added by default for tree traversal; revisit if hot queries differ.

## Impact

- **New class** in `hippo_core.yaml`: `Process`.
- **New table** in every adapter: `process`.
- **No consumer** of `process_id` yet — that lands in `provenance-as-linkml-class` (Wave 2). This change is foundation only.
- **New reference-doc section** in `reference_hippo_core.md`: `Process` slot inventory.
- **No data migration.** Fresh table; existing data untouched.

## Dependencies

- **Blocked by:** `id-registry-and-uuid-strategy`.
- **Blocks:** `provenance-as-linkml-class` (Wave 2), `computed-temporal-fields` (Wave 2).

## Acceptance

- `Process` class present in `hippo_core.yaml` with the declared slots.
- `process` table exists in SQLite and PostgreSQL via DDL generation; Neo4j stub handles the node type if the adapter is in scope.
- Creating a `Process` works through the generic `HippoClient.create` path; the create event is recorded in provenance; the registry has an entry.
- `is_a: Process` subclasses work (tested with a fixture `PipelineRun` class).
- Parent/child Process tree works; self-referential FK is functional.
- `reference_hippo_core.md` updated with the `Process` section.
- Full test suite green.
