# Computed Temporal Fields

## Why

Per sec9 §9.7, `created_at`, `updated_at`, `schema_version`, `created_by`,
and `updated_by` are never stored as columns on entity tables — they are
computed at read time by aggregating `ProvenanceRecord` entries for the
target entity. This change formalizes the read-time aggregation, adds the
required indexes on `ProvenanceRecord`, and provides a batch primitive so
list queries don't do N+1 aggregation.

Also formalizes the loud-failure behavior per sec9 §9.2 *Provenance
integrity is transactional and loud*: an entity with no provenance at
read time raises `ProvenanceIntegrityError`.

## What Changes

### Temporal fields always on reads

`HippoClient.get(entity_type, uuid)` returns an entity dict that includes:

- `created_at` — timestamp of the earliest `create` record for the entity.
- `updated_at` — timestamp of the latest record (any operation).
- `schema_version` — schema_version from the latest record.
- `created_by` — `actor_id` from the `create` record.
- `updated_by` — `actor_id` from the latest record.

Fields are computed by the SDK regardless of adapter. The adapter exposes
a `get_temporal(entity_ids)` primitive the SDK uses for batch aggregation.

### Required indexes on `ProvenanceRecord`

Added via `hippo_index` annotations in `hippo_core`:

- `(entity_id, timestamp)` — supports earliest/latest lookups with range scans.
- `(entity_id, operation, timestamp)` — supports the `create`-filtered lookup without a secondary scan.

### Batch aggregation primitive

New `StorageAdapter.get_temporal(entity_ids)` method:

- Relational adapters: one SQL statement using window functions or
  correlated subqueries; returns `dict[entity_id, TemporalRecord]`.
- Neo4j adapter: equivalent Cypher.

### Degenerate case: loud failure

An entity with no `ProvenanceRecord` entries is a data-integrity error.
`HippoClient.get` raises `ProvenanceIntegrityError` rather than returning
null temporal fields. Other inconsistencies (non-`create` as earliest,
missing `actor_id`, unrecognized `schema_version`) raise as well.

### Remove any stored temporal columns on entity tables

If any entity tables have `created_at` / `updated_at` columns (the SQLite
`entities` table does today), drop them in a migration. The values are
computed from provenance going forward.

### Actor attribution

`created_by` / `updated_by` return the `actor_id` string. Callers can
resolve to the agent entity via `HippoClient.resolve_type(actor_id)` (per
Decision 9.5.D) when richer info is needed.

## Capabilities

### New Capabilities

- `computed-temporal-fields` — temporal state derived from provenance.
- `temporal-batch-primitive` — one round-trip aggregation for list queries.
- `provenance-integrity-loud-failure` — missing/inconsistent provenance raises.

### Modified Capabilities

- `hippo-client-api` — `get` response shape gains temporal fields.
- `hippo-data-model` — entity tables shed stored temporal columns.

## Dependencies

- **Blocked by:** `provenance-as-linkml-class`.

## Acceptance

- Every entity read includes the five temporal fields.
- Index migrations applied; `EXPLAIN` confirms the expected paths.
- Batch list queries do one aggregation query per request (verified by
  logging query count).
- `ProvenanceIntegrityError` raised for entities with missing provenance
  (tested by simulated corruption).
- Stored temporal columns on entity tables are dropped; all callers
  migrated to the computed fields.
- Full suite green.
