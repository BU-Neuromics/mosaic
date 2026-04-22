# `ProvenanceRecord` as a LinkML Class

## Why

Hippo's provenance log currently lives outside the LinkML schema system —
a hand-coded Python `ProvenanceStore` manages its own table and semantics.
sec9 §9.6 moves `ProvenanceRecord` into `hippo_core` as a first-class
LinkML class with formal PROV-O alignment, so it flows through the same
DDL, validation, introspection, and diff paths as user entities.

This is the load-bearing Wave 2 change. It depends on Wave 1's
`process-class` (ProvenanceRecord's `process_id` references `Process`)
and `hippo-core-schema` (inherits `Entity`). Also declares the
`hippo_append_only` annotation in `hippo_ext` alongside its consumer
(Decision 9.4.B).

## What Changes

### Declare `ProvenanceRecord` in `hippo_core`

Per sec9 §9.6:

- `is_a: Entity` (inherits id + is_available).
- `class_uri: prov:Activity` (atomic scale; shares the URI with `Process` at the composite scale).
- Annotated `hippo_append_only: true` (see §hippo_ext below).
- Slots: `entity_id`, `entity_type`, `operation`, `actor_id`, `timestamp`, `schema_version`, `derived_from_id`, `process_id`, `patch`, `context`. See sec9 §9.6 for types, requiredness, and PROV-O mappings.

### Declare `hippo_append_only` in `hippo_ext`

`provenance-as-linkml-class` owns the declaration of `hippo_append_only`
per Decision 9.4.B. Add:

- `hippo_append_only` slot in `hippo_ext.yaml` with `range: boolean`,
  `in_subset: [class_annotation]`, `ifabsent: "false"`.
- Document in `reference_hippo_ext.md`.
- Bump `hippo_ext` minor version.

### Adapter write-guard

Storage adapters honor `hippo_append_only: true` by rejecting updates
and deletes against the annotated class's table. Implementation:

- SQLiteAdapter and PostgresAdapter gain a registry of append-only
  classes, populated from the merged SchemaView at startup.
- Writes that target an append-only class go through the normal INSERT
  path; UPDATE/DELETE on an append-only class raises an error before
  touching the DB.

### Write atomicity

Every entity mutation and its `ProvenanceRecord` write are one
transactional unit (sec9 §9.6). Existing `ProvenanceStore` already runs
in the same transaction as entity writes; this change ensures the
invariant remains explicit after `ProvenanceRecord` is LinkML-declared.

### `Operation` enum migration

The existing hand-coded operation constants (`"CREATE"`, `"UPDATE"`, etc.)
are replaced by `Operation` enum values from `hippo_core` (lowercase
snake_case per the enum). Audit the codebase for hardcoded operation
strings and migrate.

### System events stay in the same table

Per sec9 §9.6's *single-table* decision, `migration_applied` and
`reference_data_installed` records live in `ProvenanceRecord` with
`entity_id = null`. No separate `system_events` table.

## Capabilities

### New Capabilities

- `provenance-as-linkml-class` — `ProvenanceRecord` declared in
  `hippo_core` with full PROV-O alignment.
- `hippo_append_only-enforcement` — adapters reject UPDATE/DELETE on
  append-only classes.

### Modified Capabilities

- `hippo-data-model` — provenance is now schema-declared.
- `hippo-ext-vocabulary` — gains `hippo_append_only`.
- `hippo-core-schema` — gains `ProvenanceRecord`.

## Dependencies

- **Blocked by:** `hippo-core-schema`, `process-class` (Wave 1).
- **Blocks:** `computed-temporal-fields` (Wave 2).

## Acceptance

- `ProvenanceRecord` appears in `hippo_core` and validates against
  `linkml-validate`.
- `hippo_append_only` declared in `hippo_ext.yaml` and documented in
  `reference_hippo_ext.md`.
- SQLite and PostgreSQL adapters reject UPDATE and DELETE on rows of
  any append-only class (tested).
- Existing provenance behavior preserved — tests that read
  `ProvenanceStore` output continue to pass, now backed by the
  LinkML-declared class.
- `Operation` enum values used throughout the codebase (no lingering
  hardcoded operation strings).
- Migration / reference-data events coexist with entity events in the
  same table.
