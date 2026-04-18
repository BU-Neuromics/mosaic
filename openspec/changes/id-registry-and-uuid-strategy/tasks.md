# Tasks — `id-registry-and-uuid-strategy`

## 1. Formalize UUID invariant in `hippo_core`

- [ ] 1.1 Add a UUID `pattern` (or equivalent constraint) to `Entity.id` in `hippo_core.yaml`.
- [ ] 1.2 Document the invariant in `reference_hippo_core.md`: `id` is SDK-assigned, UUID-typed, opaque to callers.
- [ ] 1.3 Update the SDK to reject caller-supplied non-UUID ids at `create` with a clear error.
- [ ] 1.4 Choose UUIDv7 where available (Python 3.11+'s `uuid.uuid7()` when it lands; or a shim for UUIDv7 generation). Fall back to v4 otherwise.
- [ ] 1.5 Unit test: caller supplying a non-UUID id is rejected; SDK-generated id is a valid UUID.

## 2. `_entity_registry` table DDL

- [ ] 2.1 Add `_entity_registry(id TEXT PRIMARY KEY, entity_type TEXT NOT NULL, created_at DATETIME NOT NULL)` to the SQLite adapter's DDL generator.
- [ ] 2.2 Same for the PostgreSQL adapter; use `uuid` column type instead of `TEXT` and `TIMESTAMPTZ` for `created_at`.
- [ ] 2.3 Create a secondary index on `entity_type` for "list all entities of type X" queries.
- [ ] 2.4 Add an Alembic-style migration (or equivalent) that creates the table on upgrade.
- [ ] 2.5 Test: DDL generation produces the expected `CREATE TABLE` / `CREATE INDEX` for both adapters.

## 3. Populate the registry on every entity create

- [ ] 3.1 Extend `StorageAdapter` abstract class with `register_entity(id, entity_type)` and `unregister_entity(id)` (for the rare hard-purge path).
- [ ] 3.2 Implement in `SQLiteAdapter`: `INSERT INTO _entity_registry(id, entity_type, created_at) VALUES (?, ?, ?)`. Called inside the same transaction as the entity insert.
- [ ] 3.3 Implement in `PostgresAdapter`: same pattern with PG types.
- [ ] 3.4 Implement in `Neo4jAdapter` stub (if/when present): no-op; native labels already serve the purpose.
- [ ] 3.5 Wire `register_entity` into `create_entity` and `supersede_entity` (both create new entities).
- [ ] 3.6 Transactional guarantee test: simulate an insert failure after registry write → both rollback; no orphan registry row.

## 4. Type-resolution helpers

- [ ] 4.1 Add `StorageAdapter.lookup_type(id) -> str | None` abstract method.
- [ ] 4.2 Add `StorageAdapter.lookup_types(ids) -> dict[str, str]` abstract method; batch variant.
- [ ] 4.3 Relational implementation: `SELECT id, entity_type FROM _entity_registry WHERE id IN (...)`.
- [ ] 4.4 Neo4j implementation (when present): `MATCH (n:Entity) WHERE n.id IN $ids RETURN n.id, labels(n)`; filter for the concrete class label excluding `:Entity`.
- [ ] 4.5 Expose `HippoClient.resolve_type(uuid)` and `HippoClient.resolve_types(uuids)`; raise `UnknownEntityError` on unresolved UUIDs.
- [ ] 4.6 Update `HippoClient.get` to accept a UUID alone and resolve the type via the registry; preserve the `client.get(entity_type, uuid)` overload for back-compat and performance.

## 5. Backfill migration for existing deployments

- [ ] 5.1 Author a one-time migration step that walks every known entity table and inserts `(id, entity_type, created_at)` rows into `_entity_registry`. `INSERT OR IGNORE` / `ON CONFLICT DO NOTHING` for idempotence.
- [ ] 5.2 Migration is resumable: if interrupted, re-running picks up where it left off.
- [ ] 5.3 On completion, emit a `migration_applied` provenance event noting the backfilled row count. (Uses existing provenance mechanism; the LinkML-class migration of `ProvenanceRecord` is a later change.)
- [ ] 5.4 Test: pre-populate a fixture DB with entities, run the migration, verify every entity has a registry row and the event was emitted.

## 6. Performance benchmarks

- [ ] 6.1 Benchmark single-entity `create` before and after this change; target <15% slowdown.
- [ ] 6.2 Benchmark batch ingest (1000 entities) before and after; target <5% slowdown.
- [ ] 6.3 Benchmark polymorphic resolution (`client.get(uuid)`): cold vs. warm; target <1ms cold at 100k entities, <100 µs warm.
- [ ] 6.4 Document the numbers in `sec9_decisions.md` under the 9.5 identity-model decision (or a new 9.5.A entry) as measured values.

## 7. Tests

- [ ] 7.1 Unit: create → registry row present with correct `entity_type` (FQN form).
- [ ] 7.2 Unit: `client.get(uuid)` without type hint returns the right entity.
- [ ] 7.3 Unit: `resolve_types(list_of_uuids)` returns correct types; raises on unknown ids.
- [ ] 7.4 Unit: insert-failure simulation → no orphan registry row.
- [ ] 7.5 Integration: backfill migration populates a fixture DB correctly.
- [ ] 7.6 Integration: `client.get(uuid)` works for entities created before the change (post-backfill).
- [ ] 7.7 Unit: Neo4j adapter stub (if present) resolves types via labels without touching a registry table.

## 8. Documentation

- [ ] 8.1 Update `reference_hippo_core.md`'s `Entity.id` description with the UUID invariant and reject-on-caller-supplied rule.
- [ ] 8.2 Document `_entity_registry` in the relational-adapter section of `reference_hippo_yaml.md` (or in sec3b as part of its later revision; cross-reference for now).
- [ ] 8.3 Update sec9 §9.5's identity-model table if any cost estimates or mechanisms drift during implementation.

## 9. Acceptance check

- [ ] 9.1 `_entity_registry` exists and is correctly populated on every create.
- [ ] 9.2 `client.get(uuid)` works without an `entity_type` argument.
- [ ] 9.3 Backfill migration completes successfully on a pre-existing fixture DB.
- [ ] 9.4 Performance regression targets met (<15% single, <5% batch, <1ms cold resolution at 100k scale).
- [ ] 9.5 Full test suite green.
