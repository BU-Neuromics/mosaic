# Tasks — `provenance-as-linkml-class`

## 1. Declare `hippo_append_only` in `hippo_ext`

- [ ] 1.1 Add `hippo_append_only` to `src/hippo/schemas/hippo_ext.yaml` with `range: boolean`, `in_subset: [class_annotation]`, `ifabsent: "false"`, and a description matching sec9 §9.4.
- [ ] 1.2 Document in `design/reference_hippo_ext.md` (new Wave 2 row in the vocabulary table).
- [ ] 1.3 Bump `hippo_ext` minor version (e.g., `0.2.0`).

## 2. Declare `ProvenanceRecord` in `hippo_core`

- [ ] 2.1 Add class `ProvenanceRecord` to `hippo_core.yaml` with `is_a: Entity`, `class_uri: prov:Activity`, and `annotations: {hippo_append_only: true}`.
- [ ] 2.2 Declare slots per sec9 §9.6: `entity_id`, `entity_type`, `operation` (range `Operation`), `actor_id`, `timestamp`, `schema_version`, `derived_from_id`, `process_id`, `patch` (range `string` with JSON-in-string convention), `context` (same).
- [ ] 2.3 Index appropriate slots via `hippo_index`: `(entity_id)`, `(timestamp)`, `(operation)`, `(process_id)`.
- [ ] 2.4 Bump `hippo_core` minor version.
- [ ] 2.5 Validate via `linkml-validate`.

## 3. Adapter write-guard for `hippo_append_only`

- [ ] 3.1 Add `SchemaRegistry.append_only_classes()` → set of class names marked `hippo_append_only: true`.
- [ ] 3.2 Plumb the set into `SQLiteAdapter` (and `PostgresAdapter`) at startup.
- [ ] 3.3 Reject `UPDATE` against an append-only class (raise a Hippo `SchemaError` or equivalent).
- [ ] 3.4 Reject `DELETE` (hard delete) against an append-only class. Note: `availability_change` via `update(is_available=False)` is still forbidden — append-only means append-only.
- [ ] 3.5 Tests: UPDATE / DELETE rejected; INSERT allowed; error messages name the class.

## 4. Migrate existing provenance code

- [ ] 4.1 Audit uses of hardcoded operation strings (`"CREATE"`, `"UPDATE"`, `"AVAILABILITY_CHANGE"`, etc.) in `ProvenanceStore` and surrounding code. Replace with `Operation` enum values.
- [ ] 4.2 The existing `ProvenanceStore` table becomes the LinkML-generated `provenance_record` table. Migrate: drop/rename the old table (or keep a view) and re-populate via DDL from `hippo_core`.
- [ ] 4.3 Preserve the existing provenance API surface (`ProvenanceStore.record`, etc.) or migrate callers to the new path; whichever is smaller.
- [ ] 4.4 Confirm the transaction boundary: every entity mutation + its ProvenanceRecord write share the same transaction.

## 5. System events coexist

- [ ] 5.1 Verify `migration_applied` and `reference_data_installed` records are emitted into the same `provenance_record` table with `entity_id = null`.
- [ ] 5.2 Queries filtering `entity_id IS NULL AND operation = 'migration_applied'` work.

## 6. Tests

- [ ] 6.1 DDL generation produces the `provenance_record` table with correct columns and indexes.
- [ ] 6.2 Create an entity; ProvenanceRecord is written in the same transaction.
- [ ] 6.3 Insert-failure rollback test: simulated adapter failure rolls back the entity write AND the provenance write.
- [ ] 6.4 UPDATE / DELETE on ProvenanceRecord fails.
- [ ] 6.5 Multi-entity scenario (e.g., reference load): multiple ProvenanceRecords share a `process_id`; grouping by `process_id` returns the whole set.
- [ ] 6.6 System-event queries with `entity_id = null`.

## 7. Documentation

- [ ] 7.1 Update `design/reference_hippo_core.md` with a `ProvenanceRecord` section mirroring the `Process` / `Entity` pattern.
- [ ] 7.2 Update sec6 (Provenance spec) per sec9's revision plan — light touch on the existing sec6 content, pointing at sec9 §9.6 for the canonical shape.
- [ ] 7.3 Log any opinionated implementation calls in `design/sec9_decisions.md`.

## 8. Acceptance

- [ ] 8.1 `ProvenanceRecord` in `hippo_core`; `hippo_append_only` in `hippo_ext`.
- [ ] 8.2 DDL and append-only enforcement work on SQLite; Postgres parity covered.
- [ ] 8.3 Transaction atomicity preserved; insert-failure rollback tested.
- [ ] 8.4 System events coexist in the same table.
- [ ] 8.5 Full test suite green.
