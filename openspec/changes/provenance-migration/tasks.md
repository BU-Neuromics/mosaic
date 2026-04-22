# Tasks — `provenance-migration`

## 1. DDL migration

- [ ] 1.1 Remove the hand-coded `CREATE TABLE IF NOT EXISTS provenance (...)` and `CREATE INDEX` blocks from `SQLiteAdapter._init_schema`. Postgres equivalent in `PostgresAdapter`.
- [ ] 1.2 The `provenance_record` table is emitted by the LinkML DDL generator from `hippo_core.ProvenanceRecord`. Verify the generated DDL includes the expected columns and indexes (entity_id, operation, timestamp, process_id).
- [ ] 1.3 One-time data-migration step (if any rows exist in the legacy `provenance` table): `INSERT INTO provenance_record SELECT ... FROM provenance` mapping columns per the proposal table; drop `provenance` when done. Since there are no production deployments, a simpler drop-and-recreate path is acceptable for local dev DBs.

## 2. ProvenanceStore rewrite

- [ ] 2.1 Update `ProvenanceStore.record(...)` signature to sec9 §9.6's parameters: `entity_id`, `entity_type`, `operation` (accept enum or compatibility string), `actor_id`, `schema_version` (SDK-captured), `derived_from_id=None`, `process_id=None`, `patch=None`, `context=None`.
- [ ] 2.2 Insert into `provenance_record` with the new column names.
- [ ] 2.3 `find_by_entity(entity_id, operation=None)`, `get_history(entity_id)` return records with the new field shape.
- [ ] 2.4 Compatibility shim: accept legacy string operations (`"CREATE"`, `"UPDATE"`, `"AVAILABILITY_CHANGE"`, `"SOFT_DELETE"`, `"SUPERSEDE"`) and map to `Operation` enum values. Remove the shim after all callers are migrated.
- [ ] 2.5 Drop `compute_state_hash` helper — no longer needed (sec9 has no prior-state-hash concept).
- [ ] 2.6 Drop `state_snapshot` parameter — redundant with `patch`.
- [ ] 2.7 `schema_version` captured from the SchemaRegistry at write time; never caller-supplied.

## 3. `Operation` enum migration

- [ ] 3.1 Grep for hardcoded operation strings in `src/hippo/` and `tests/` — replace with `Operation` enum imports.
- [ ] 3.2 `"SOFT_DELETE"` and `"AVAILABILITY_CHANGE"` both map to `Operation.availability_change`; the Status driver (soft-delete vs archive vs distribute) is carried in `patch`.
- [ ] 3.3 Confirm: no remaining references to legacy operation strings in the codebase.

## 4. `hippo_append_only` enforcement via SQL triggers (Decision 9.6.C)

- [x] 4.1 Add `SchemaRegistry.append_only_classes()` returning the set of class names with `hippo_append_only: true`. (landed in commit 1 — available for future DDL-generator-driven trigger emission but not consumed by adapters in this commit.)
- [ ] 4.2 Update `sqlite_triggers.py` to target the new `ProvenanceRecord` table with new column names. Replace the five column-specific UPDATE triggers with a single `BEFORE UPDATE` trigger covering any column, any row. Retain the `BEFORE DELETE` trigger.
- [ ] 4.3 Update `SQLiteAdapter._init_schema` to create triggers after the LinkML-generated `ProvenanceRecord` table exists.
- [ ] 4.4 PostgresAdapter: equivalent `CREATE TRIGGER` definitions (PL/pgSQL `RAISE EXCEPTION` replaces SQLite's `RAISE ABORT`).
- [ ] 4.5 Tests: UPDATE and DELETE against `ProvenanceRecord` raise; INSERT succeeds. Test message format ("hippo_append_only class").

## 5. Test suite updates

- [ ] 5.1 `tests/core/test_provenance.py`: column-name assertions updated (`operation_type` → `operation`, `payload` → `patch`, `user_context` → `actor_id`). Delete tests specific to `previous_state_hash` / `state_snapshot` (concepts no longer exist) — keep coverage for the concept they addressed (lineage is now tested via `derived_from_id`; state capture is now tested via `patch`).
- [ ] 5.2 `tests/core/test_supersede_entity.py`: assertions that exercise the supersede operation updated to use `Operation.supersede`; `derived_from_id` now tested alongside.
- [ ] 5.3 `tests/core/test_bulk_availability.py`: `"SOFT_DELETE"` / `"AVAILABILITY_CHANGE"` → `Operation.availability_change`.
- [ ] 5.4 `tests/integration/test_postgres_adapter.py`: same renames for the PG adapter path.
- [ ] 5.5 Write new tests that exercise the sec9 §9.6 fields explicitly — `schema_version` populated from registry, `derived_from_id` set on supersede, `process_id` correlation across a multi-entity operation.

## 6. Decision log

- [ ] 6.1 Add Decision 9.6.B logging the actor back-population call (recommend Option A — leave legacy strings as-is). Note any other opinionated calls that surface during implementation.

## 7. Documentation

- [ ] 7.1 Update `design/reference_hippo_core.md` — remove the "storage migration deferred" scope note in the ProvenanceRecord section (now active).
- [ ] 7.2 Update `design/reference_hippo_ext.md` `hippo_append_only` section — remove the "enforcement lands in follow-up" caveat.
- [ ] 7.3 Revise sec6 (Provenance spec) per sec9's revision plan — light touch; point at sec9 §9.6 as authoritative.

## 8. Acceptance

- [ ] 8.1 `provenance_record` table present; legacy `provenance` table gone.
- [ ] 8.2 UPDATE / DELETE against `provenance_record` rejected by the adapter.
- [ ] 8.3 No legacy operation strings remain in src/ or tests/.
- [ ] 8.4 `ProvenanceStore` API aligned with sec9 §9.6; schema_version captured.
- [ ] 8.5 Full test suite green.
