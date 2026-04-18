# Identity Registry and UUID Strategy

## Why

Polymorphic references on forthcoming classes — `ProvenanceRecord.entity_id` (any domain class), `ProvenanceRecord.actor_id` (user, service, system, or `Process`), `ProvenanceRecord.process_id` (`Process`), `Process.parent_process_id` (self-ref), `ProvenanceRecord.derived_from_id` (any domain class) — carry a UUID with no structural type tag. A caller holding a UUID must be able to resolve it to a specific entity class without additional information.

Hippo already uses UUIDs for entity identifiers (per the existing "Upsert identity resolution" decision and GA4GH DRS work); this change formalizes the invariant and builds the type-resolution seam every subsequent change assumes.

Per sec9 §9.2 and §9.5, type resolution is adapter-specific:

- **Relational adapters** (SQLite, PostgreSQL) maintain an `_entity_registry` table keyed on `id`, populated in the same transaction as every entity create. Maps `id → entity_type`.
- **Neo4j adapter** (future) uses native node labels.
- The SDK contract `client.get(uuid)` is uniform across adapters.

This change is Wave 1 #3 per sec9 §9.12. It depends on `hippo-core-schema` (needs `Entity` declared so the registry can FK to a uniform concept) and blocks `process-class` and everything downstream.

## What Changes

### Formalize the UUID invariant

- Every entity `id` is a UUID. Version: prefer UUIDv7 (time-ordered) when the environment supports it; fall back to v4. The SDK assigns on `create`; callers MUST NOT supply ids.
- `ProvenanceRecord.id`, `Process.id`, and every user-schema domain class's `id` slot inherit this invariant via `is_a: Entity`.
- Document the invariant in `hippo_core`'s `Entity.id` slot as a `pattern` matching the UUID form; reject on write if a caller tries to supply a non-UUID id.

### `_entity_registry` table (relational adapters)

- New table in the SQLite and PostgreSQL adapters:
  ```
  _entity_registry(
    id         TEXT PRIMARY KEY,   -- UUID
    entity_type TEXT NOT NULL,      -- FQN per sec9 §9.5
    created_at DATETIME NOT NULL
  )
  ```
- `entity_type` indexed; primary key on `id` covers the dominant lookup.
- Populated on every entity create in the same transaction as the entity insert. Rolled back together on any failure.
- Not populated for `ProvenanceRecord` (its target `entity_id` is already tracked on the record itself via denormalized `entity_type`).
- Removed (or archived) only when an entity is hard-purged — an eventuality that Hippo's "no hard deletes" policy makes rare. For normal availability transitions, the registry row persists.

### SDK type-resolution helpers

- `HippoClient.resolve_type(uuid: str) -> str` — returns the FQN of the entity class; raises `UnknownEntityError` if not found.
- `HippoClient.resolve_types(uuids: list[str]) -> dict[str, str]` — batch version; one query round-trip regardless of input size.
- `HippoClient.get(uuid)` — updated to no longer require an `entity_type` hint; resolves the type via the registry, then dispatches to the correct adapter path. The previous `client.get(entity_type, uuid)` signature is preserved as an overload for back-compat and performance (skips the registry lookup).

### Adapter contract updates

- New `StorageAdapter.register_entity(id, entity_type)` abstract method; relational implementations write to `_entity_registry` in the same transaction as the entity insert. Neo4j implementations set node labels and no-op the method. Future adapters implement type resolution natively.
- New `StorageAdapter.lookup_types(ids)` for batch type resolution.
- `StorageAdapter.create_entity` and `StorageAdapter.supersede_entity` are updated to call `register_entity` inside their transaction boundary.

### Data migration for existing deployments

- On first migration after this change lands, the SQLite and PostgreSQL migrator walks every existing entity table and backfills `_entity_registry` from `(id, entity_type)`. One-time, idempotent, resumable.
- Migration emits a `migration_applied` provenance event when it completes (noting the row count backfilled).

### Tests

- Create → `_entity_registry` row exists with correct `entity_type`.
- `client.get(uuid)` without `entity_type` hint resolves correctly.
- Batch `resolve_types` returns correct types and handles partial cache misses.
- Cold resolution of an unknown UUID raises `UnknownEntityError`.
- Registry populated atomically with entity create: a simulated insert failure leaves no registry row.
- Backfill migration populates the registry for pre-existing entities.
- Write performance regression check: <15% slowdown on single-entity create; <5% on batched ingest.

## Capabilities

### New Capabilities

- `id-registry` — relational adapters maintain an `_entity_registry` table populated on every create.
- `uuid-identity` — UUID-only identity invariant formalized in `hippo_core`.
- `polymorphic-reference-resolution` — SDK resolves a bare UUID to its entity class via adapter-specific mechanisms.

### Modified Capabilities

- `hippo-architecture` — `StorageAdapter` gains `register_entity` and `lookup_types` methods.
- `hippo-data-model` — UUID invariant documented on `Entity.id`.
- `hippo-client-api` — `client.get(uuid)` works without the `entity_type` argument.

## Open Questions

- **Registry vacuum.** If an entity is hard-purged (rare per the no-hard-deletes policy), does the registry row go with it or become a tombstone? Treat as an open question; the default is "row goes with the entity" for simplicity, since purges bypass the normal lifecycle.
- **UUIDv7 rollout.** Prefer v7 for time-ordering benefits in relational indexes. If the Python version in use lacks `uuid7()`, fall back to v4 without failing. No observable behavior change to callers either way.

## Impact

- **New table** `_entity_registry` in SQLite and PostgreSQL adapters (DDL migration).
- **New abstract methods** on `StorageAdapter`.
- **Modified** `HippoClient.get` signature (backward-compat preserved via overload).
- **~10% write overhead** on entity creates (one extra INSERT per create, co-located in the transaction).
- **~O(log n) read cost** on polymorphic dereferences without a cached type hint; well-cacheable, imperceptible at Hippo's target scale per sec9 §9.5.
- **One-time backfill migration** runs on upgrade.

## Dependencies

- **Blocked by:** `hippo-core-schema` (needs `Entity` declared).
- **Blocks:** `process-class`, `provenance-as-linkml-class`, `computed-temporal-fields`, `typed-client`.

## Acceptance

- `_entity_registry` exists in SQLite and PostgreSQL adapters with the documented schema.
- Every entity create populates the registry atomically.
- `client.get(uuid)` resolves without an `entity_type` hint for any entity created after this change.
- Backfill migration populates the registry for entities created before this change.
- `resolve_type` and `resolve_types` helpers work and are tested.
- Write-performance regression under 15% on single creates and under 5% on batch ingest.
- Full test suite green, including the new resolution and backfill tests.
