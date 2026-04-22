# Tasks — `computed-temporal-fields`

## 1. Indexes on `ProvenanceRecord`

- [ ] 1.1 Annotate `ProvenanceRecord.entity_id`, `.timestamp`, `.operation` with `hippo_index: true` (may already be done during `provenance-as-linkml-class`).
- [ ] 1.2 Add a LinkML `unique_keys` or composite-index hint for the `(entity_id, timestamp)` and `(entity_id, operation, timestamp)` pairs if the DDL generator supports it; otherwise add as adapter-level index DDL.
- [ ] 1.3 Migration emits the new indexes.

## 2. Batch aggregation primitive

- [ ] 2.1 Add `StorageAdapter.get_temporal(entity_ids: list[str]) -> dict[str, TemporalRecord]` abstract method.
- [ ] 2.2 SQLite implementation: single SQL using window functions or per-entity correlated subqueries; returns dict keyed by entity_id.
- [ ] 2.3 Postgres implementation: same pattern, PG syntax.
- [ ] 2.4 Neo4j implementation (if in scope): `MATCH (e:Entity) WHERE e.id IN $ids` + aggregation across provenance relationships.

## 3. SDK temporal aggregation

- [ ] 3.1 `HippoClient.get` calls the adapter's `get_temporal` for a single entity and merges results into the returned dict.
- [ ] 3.2 `HippoClient.query` and the paginated list path call `get_temporal` once with all returned entity_ids, merging the results in one pass.
- [ ] 3.3 Add `TemporalRecord` dataclass with `created_at`, `updated_at`, `schema_version`, `created_by`, `updated_by`.

## 4. Loud failure on missing provenance

- [ ] 4.1 Add `ProvenanceIntegrityError` (new exception in `hippo.core.exceptions`).
- [ ] 4.2 Raise when `get_temporal` returns no record for a requested id (and the entity exists in the entities table).
- [ ] 4.3 Raise on consistency anomalies: earliest record with operation != `create`; missing `actor_id`; unrecognized `schema_version`.
- [ ] 4.4 Error messages name the offending entity id and describe the inconsistency shape.

## 5. Drop stored temporal columns

- [ ] 5.1 Audit the existing `entities` table in SQLite / Postgres for `created_at`, `updated_at`, `created_by`, `updated_by` columns. Create a migration that drops them.
- [ ] 5.2 Update SQLiteAdapter / PostgresAdapter to stop reading those columns; rely on `get_temporal` for the values.
- [ ] 5.3 Update any tests that assert on stored temporal columns to instead assert on the computed fields.

## 6. Tests

- [ ] 6.1 Create → read: temporal fields populated with expected values from the create event.
- [ ] 6.2 Update → read: `updated_at` advances; `created_at` unchanged.
- [ ] 6.3 Supersede → read: `updated_at` reflects the supersede event; `created_at` unchanged.
- [ ] 6.4 Availability change → read: `updated_at` reflects the change; `updated_by` is the actor.
- [ ] 6.5 Batch list of 100 entities: `get_temporal` called once, not 100 times.
- [ ] 6.6 Entity with no provenance → `ProvenanceIntegrityError` raised.
- [ ] 6.7 Non-`create` earliest record → `ProvenanceIntegrityError`.

## 7. Documentation

- [ ] 7.1 Update `design/reference_hippo_core.md` to document that temporal fields are returned on reads and derived from `ProvenanceRecord`.
- [ ] 7.2 Update sec3 / sec6 per sec9's revision plan — reaffirm the read-time-computation invariant.
- [ ] 7.3 Log any opinionated implementation calls in `sec9_decisions.md`.

## 8. Acceptance

- [ ] 8.1 Every entity read returns the five temporal fields.
- [ ] 8.2 Batch reads use one aggregation round-trip.
- [ ] 8.3 Loud failure on inconsistency works.
- [ ] 8.4 Stored temporal columns gone.
- [ ] 8.5 Full suite green.
