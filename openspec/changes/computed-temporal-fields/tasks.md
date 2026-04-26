# Tasks — `computed-temporal-fields`

## 1. Indexes on `ProvenanceRecord`

- [x] 1.1 `ProvenanceRecord.entity_id`, `.operation`, `.timestamp`, `.process_id` carry `hippo_index: true` (landed with `provenance-as-linkml-class`).
- [x] 1.2 Composite `(entity_id, timestamp)` index emitted by `SQLiteAdapter._init_database` and `PostgresAdapter._init_database` (landed with `provenance-migration`).
- [ ] 1.3 `(entity_id, operation, timestamp)` composite index — deferred. The single-column indexes plus the composite `(entity_id, timestamp)` cover the sec9 §9.7 query paths (MIN create, MAX all). Adding the three-column composite is a potential optimization once query EXPLAIN analysis motivates it.

## 2. Batch aggregation primitive

- [x] 2.1 `StorageAdapter.get_temporal(entity_ids: list[str]) -> dict[str, TemporalRecord]` added to both concrete adapters. Not declared abstract on the ABC per Decision 9.7.G (duck-typed extension, matches existing pattern).
- [x] 2.2 SQLite implementation: one SQL round-trip using a CTE + correlated subqueries for actor_id and schema_version of the earliest/latest records.
- [x] 2.3 Postgres implementation: same CTE pattern, Postgres JSON syntax.
- [ ] 2.4 Neo4j implementation — deferred until the Neo4j adapter lands.

## 3. SDK temporal aggregation

- [x] 3.1 `HippoClient.get` → `QueryService.get` calls `storage.get_temporal([entity_id])` and merges the TemporalRecord into the returned dict.
- [x] 3.2 `HippoClient.query` → `QueryService.query` calls `storage.get_temporal(result_ids)` once per page. Batch test verifies exactly one invocation.
- [x] 3.3 `TemporalRecord` dataclass added to `hippo.core.types` with `created_at`, `updated_at`, `schema_version`, `created_by`, `updated_by`.

## 4. Loud failure on missing provenance

- [x] 4.1 `ProvenanceIntegrityError` added to `hippo.core.exceptions` with `entity_id` and `inconsistency` fields.
- [x] 4.2 Raised from `QueryService.get` when `get_temporal` returns no record for the requested id.
- [x] 4.3 Raised from `QueryService.query` when any result-set entity has no provenance (Decision 9.7.F — whole-page failure). Also raises when `temporal.created_at is None` (provenance rows exist but no `create` among them).
- [ ] 4.4 Error messages name the offending entity id and describe the inconsistency shape — done (message + `inconsistency` field).

## 5. Drop stored temporal columns

- [x] 5.1 The `entities` table `created_at` / `updated_at` columns are dropped. A forward migration (`ALTER TABLE entities DROP COLUMN`) runs in `_run_migrations` (SQLite, idempotent via PRAGMA table_info guard) and in `_init_database` (Postgres, `DROP COLUMN IF EXISTS`). All callers — adapters, ingestion service, provenance service, query service, batch fetcher, tests — migrated to the provenance-only path. PTS-69.
- [ ] 5.2 Same for `created_by` / `updated_by` — not currently stored as columns; read path populates them from provenance directly.

## 6. Tests

- [x] 6.1 Create → read surfaces all five fields (`test_get_surfaces_all_five_fields`, `test_created_at_populated_from_create_event`).
- [x] 6.2 Update → read: `updated_at` advances, `created_at` unchanged (`test_updated_at_advances_on_update`).
- [x] 6.3 Supersede — transitively covered by `test_supersede_entity.py` (the `supersede` operation records a new ProvenanceRecord and thus a new `updated_at`).
- [x] 6.4 Availability change does not advance `updated_at` for deletion events (`test_availability_change_does_not_advance_updated_at`). This matches the legacy `SOFT_DELETE` exclusion per Decision 9.6.B.
- [x] 6.5 Batch list runs exactly one aggregation query (`test_query_does_batch_aggregation` — spy-based verification).
- [x] 6.6 Entity with no provenance → `ProvenanceIntegrityError` (`test_missing_provenance_raises`; query-path version `test_query_raises_on_orphan_entity_in_page`).
- [x] 6.7 Non-`create` earliest record → `ProvenanceIntegrityError` (`test_missing_create_record_raises`).

## 7. Documentation

- [ ] 7.1 `design/reference_hippo_core.md` — temporal fields on reads. Deferred to a separate docs touch-up.
- [ ] 7.2 Sec3 / sec6 revision per sec9's plan. Deferred to the broader sec6 rewrite.
- [x] 7.3 Opinionated calls logged in `sec9_decisions.md` as 9.7.E (schema_version derivation), 9.7.F (query-path loud failure), 9.7.G (duck-typed primitive).

## 8. Acceptance

- [x] 8.1 Every entity read returns the five temporal fields.
- [x] 8.2 Batch reads use one aggregation round-trip (verified by spy test).
- [x] 8.3 Loud failure on inconsistency works (both `get` and `query` paths).
- [x] 8.4 Stored temporal columns gone — `created_at` and `updated_at` dropped from the `entities` table in both SQLite and Postgres adapters. The SDK computes exclusively via `get_temporal`. All 932 tests pass. PTS-69.
- [x] 8.5 Full suite green (864 passed, 7 skipped).
