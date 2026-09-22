# Batch Unit-of-Work (whole-set dry-run validation + atomic multi-entity write)

Tracking issue: BU-Neuromics/hippo#84

## Why

Hippo's write boundary is **per single entity** today: `HippoClient.put()` →
`IngestionService._put_with_sqlite()` → `SQLiteAdapter.create()/update_data()`
each wrap exactly one `_transaction()` (confirmed in design/sec11 §11.8.1). A
`--atomic` batch flag is noted as deferred in design/sec5 §5.4, and `dry_run`
today means *"don't write"*, not *"validate without writing"* — there is no
public path to validate a **set** of related entities before committing.

Consumers that build guided **multi-step, multi-entity workflows** (the Aperture
interface layer's write loop — see `aperture/design/portal-requirements.md` X4 /
L9 / L10) therefore have to either accept partially-written graphs on failure or
hand-roll a saga/compensation scheme on the client. The cleaner, SDK-first
design is **stage → whole-set dry-run validate → atomic commit**: nothing enters
the domain graph until the entire related set is known valid, then it commits as
a unit. Hippo already owns the transactional machinery to do this
(`SQLiteAdapter.staged_transaction()` — reference-counted, commit-all-or-rollback,
used by the lifecycle/migration orchestrator), so this exposes existing
capability rather than building distributed transactions.

## What Changes

Delivered in two increments under one capability.

### Increment 1 — Whole-set dry-run validation (this change's first PR)

- New SDK API `HippoClient.validate_batch(operations, *, assign_ids=True) ->
  BatchValidationResult`.
- New aggregated result type `BatchValidationResult` (overall validity + ordered
  per-entity `ValidationResult`, with `failures`/`errors`/`invalid_results`/
  `to_envelope` accessors; reuses the sec9 §9.9 envelope).
- Runs the standard per-entity validation pipeline (LinkML → CEL → Python) over
  each operation and **aggregates** (not fail-fast across the set).
- Assigns **in-memory provisional ids** (on copies, never mutating caller data)
  to id-less operations so each result is addressable and a future atomic write
  can resolve references between set members.
- **Performs zero writes** — neither entity tables nor the provenance log are
  touched.

### Increment 2 — Atomic multi-entity write (planned)

- New SDK API `HippoClient.batch_put(operations, dry_run=False) ->
  BatchWriteResult`: assign ids up front → resolve intra-batch references →
  validate the whole set → if valid and not `dry_run`, wrap **all** creates/
  updates (and any deferred relationship edges) in one `staged_transaction()`;
  any failure rolls back the entire set.
- Relationship edges deferred until after entity writes within the same
  transaction so intra-batch forward references resolve (today
  `RelationshipManager.relate()` requires the target to already exist).

### Increment 3 — Transport exposure (planned)

- REST `POST /ingest/batch` and a GraphQL `ingestBatch(entities, dryRun)`
  mutation, thin wrappers over the SDK, returning per-entity status/failures.

## Capabilities

### New Capabilities

- `whole-set-dry-run-validation` — validate a proposed set of entities,
  aggregating per-entity outcomes, without writing. *(Increment 1 — landed.)*
- `atomic-multi-entity-write` — commit a related set all-or-nothing via a single
  staged transaction. *(Increment 2 — planned.)*

### Modified Capabilities

- `hippo-client-api` — gains `validate_batch` (and later `batch_put`).

## Dependencies

- Builds on the existing `staged_transaction()` primitive (increment 2).
- Driver / cross-reference: Aperture `design/portal-requirements.md` X4.

## Acceptance

### Increment 1 (this PR)

- `HippoClient.validate_batch([...])` returns a `BatchValidationResult` with
  overall validity + per-entity tier-annotated failures, performing **zero**
  writes (asserted against storage).
- A set mixing valid and invalid entities reports every outcome (aggregated, not
  fail-fast).
- Id-less operations receive an in-memory provisional id without mutating the
  caller's data.
- No change to existing single-write behavior; full suite green.

### Increment 2 (later)

- `batch_put` commits a valid related set atomically and rolls the whole set
  back on any failure (asserted: no partial writes, no orphan provenance).
- An entity referencing another entity created in the same set commits
  successfully (intra-batch forward reference resolved).
