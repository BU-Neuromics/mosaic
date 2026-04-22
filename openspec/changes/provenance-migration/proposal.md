# Provenance Storage Migration onto `ProvenanceRecord`

## Why

`provenance-as-linkml-class` declared `ProvenanceRecord` in `hippo_core`
for introspection and downstream use (typed-client, REST surface). The
actual storage — the `provenance` table, the `ProvenanceStore` class,
and every caller — still uses the legacy shape with `operation_type`,
`previous_state_hash`, `state_snapshot`, `operation_id`, etc. This change
migrates the implementation onto the LinkML-declared `ProvenanceRecord`
shape per sec9 §9.6.

Scoped as a dedicated change per Decision 9.6.A because the migration
involves opinionated calls about legacy fields (drop
`previous_state_hash`, drop `state_snapshot`, etc.) and ~40 existing
test references that need per-case attention — wrapping it into
`provenance-as-linkml-class` would have obscured those decisions.

## What Changes

### Replace the `provenance` table with `provenance_record`

The hand-coded DDL in `SQLiteAdapter._init_schema` (and the Postgres
equivalent) creating the `provenance` table is removed. Instead, the
LinkML DDL generator produces a `provenance_record` table from
`hippo_core.ProvenanceRecord` — same pipeline as every other entity
class.

### Map legacy fields onto sec9 §9.6 slots

| Legacy column | sec9 slot | Treatment |
|---|---|---|
| `id` (INTEGER AUTOINCREMENT) | `id` (UUID string) | SDK generates UUID on insert. |
| `entity_id` | `entity_id` | Unchanged. Now references the identity model (sec9 §9.5). |
| `entity_type` | `entity_type` | Unchanged. FQN. |
| `operation_type` (TEXT: "CREATE", "UPDATE", …) | `operation` (Operation enum, lowercase snake_case) | Map at write — `"CREATE"` → `Operation.create`, etc. |
| `timestamp` (TEXT ISO8601) | `timestamp` (datetime) | Unchanged semantically. |
| `user_context` (TEXT) | `actor_id` (UUID string) | Rename. Semantic shift: previously free-form string; now a UUID per sec9 §9.5 identity model. Migration: existing rows' `user_context` becomes `actor_id` as-is (not a valid UUID for legacy data, but acceptable for an append-only audit log — historical records retain their historical actor string). |
| `payload` (TEXT JSON) | `patch` (string JSON) | Rename. |
| `operation_id` (TEXT UUID) | — | Drop. Redundant with `id` under the new UUID-identity model. |
| `previous_state_hash` (TEXT SHA-256) | — | Drop. sec9 has no prior-state-hash concept; supersession lineage is `derived_from_id`, not a hash chain. |
| `state_snapshot` (TEXT JSON) | — | Drop. Redundant with `patch` under the new model. |
| — | `schema_version` | New. SDK captures from `SchemaRegistry` at write time. |
| — | `process_id` | New. Optional FK to `Process`. |
| — | `derived_from_id` | New. For `supersede` operations. |
| — | `context` (string JSON) | New. Caller-supplied metadata. |

### Rewrite `ProvenanceStore`

- `record(...)` signature updated to sec9 §9.6's parameter set.
- Emits `operation` as an `Operation` enum value; legacy callers passing
  `"CREATE"` continue to work via a compatibility shim that maps strings
  to enum values during the transition period (then shim is removed).
- Captures `schema_version` from the registry.
- `find_by_entity` / `get_history` query the `provenance_record` table
  and return records with the new field shape.

### Adapter write-guard for `hippo_append_only`

Runtime check in SQLiteAdapter and PostgresAdapter: when a write targets
a class marked `hippo_append_only: true`, any non-INSERT (UPDATE or
DELETE) is rejected with a clear error. Implementation:

- `SchemaRegistry.append_only_classes()` helper returning the set of
  class names annotated with `hippo_append_only: true`.
- Adapters plumb this set through at startup.
- Attempts to UPDATE or DELETE rows of an append-only class raise a
  Hippo-level error before touching the DB.

### Existing test suite updates

Per the audit, ~40 test references need attention:

- `test_provenance.py`: update column-name assertions (`operation_type`
  → `operation`), drop tests specific to `previous_state_hash` and
  `state_snapshot` (their concepts don't exist in sec9).
- `test_postgres_adapter.py`, `test_bulk_availability.py`,
  `test_supersede_entity.py`: same renames; drop or adapt tests that
  specifically exercise legacy fields.
- Replace the legacy operation constants (`"CREATE"`, `"UPDATE"`,
  `"SOFT_DELETE"`, `"AVAILABILITY_CHANGE"`, `"SUPERSEDE"`, etc.) with
  `Operation.create`, `Operation.update`, `Operation.availability_change`,
  `Operation.supersede` enum values. `"SOFT_DELETE"` maps to
  `availability_change` with the Status carried in `patch` — no longer
  a distinct operation kind.

### One-time data migration

If a deployment has a populated `provenance` table, a one-time migration:

1. `CREATE TABLE provenance_record (...)` via the LinkML DDL path.
2. `INSERT INTO provenance_record SELECT ... FROM provenance` mapping
   legacy columns onto the new shape; emit synthetic UUIDs for `id`,
   skip `operation_id` / `previous_state_hash` / `state_snapshot`,
   copy `user_context` to `actor_id` as-is, `payload` to `patch`.
3. `DROP TABLE provenance`.

Idempotent and resumable. Wrapped in a migration script surfaced by
`hippo migrate`.

Since there are no production deployments (per earlier user directive),
the migration can be simpler: drop-and-recreate is acceptable for local
dev databases. The migration code still exists for future production
use but its strict correctness is not exercised during development.

## Capabilities

### New Capabilities

- `provenance-storage-migration` — `provenance_record` table replaces
  the legacy `provenance` table; `ProvenanceStore` operates on the
  LinkML shape.
- `hippo_append_only-enforcement` — adapter write-guard rejecting
  UPDATE / DELETE on append-only classes.

### Modified Capabilities

- `hippo-provenance` — backing storage + `ProvenanceStore` API shape.
- `hippo-data-model` — drops legacy provenance fields.

## Open Questions

### Actor back-population

Legacy rows have `user_context` as a free-form string (often a username
or "sqlite_adapter"). After rename to `actor_id`, these strings won't
resolve through the UUID identity model. Options:

- **A.** Leave as-is — historical audit records retain historical
  actor strings; new records use UUIDs.
- **B.** Synthesize a `LegacyActor` placeholder entity per unique
  legacy string, back-populate references.

Option A is simpler and matches append-only semantics (you don't
rewrite history). Recommend A; flag in sec9_decisions.md at
implementation time.

### Batch/transaction semantics

sec9 §9.6 requires transactional write atomicity — entity mutation +
ProvenanceRecord write share a transaction. `ProvenanceStore` already
operates inside the existing entity-write transaction; this change
preserves that and adds an explicit test.

## Impact

- **DDL migration**: `provenance` table goes away, `provenance_record`
  table appears. Single migration step.
- **API breakage**: `ProvenanceStore.record` signature changes; every
  caller updated.
- **Test churn**: ~40 test references updated; some deleted outright.
- **Adapter changes**: SQLite + Postgres both need the write-guard.

## Dependencies

- **Blocked by:** `provenance-as-linkml-class` (Wave 2 — provides the
  LinkML declaration).
- **Blocks:** `computed-temporal-fields` (Wave 2 — its aggregation
  queries the `provenance_record` table directly).

## Acceptance

- `provenance_record` table exists and is DDL-generated from
  `hippo_core.ProvenanceRecord`.
- Legacy `provenance` table removed.
- `ProvenanceStore` API aligned with sec9 §9.6.
- Legacy operation strings replaced by `Operation` enum throughout.
- `hippo_append_only` adapter enforcement active: UPDATE / DELETE on
  `provenance_record` raises; INSERT succeeds.
- Full test suite updated and green.
- `reference_hippo_core.md` scope-note updated to remove the
  "storage migration deferred" caveat.
