# Tasks — `batch-unit-of-work`

Tracking issue: BU-Neuromics/hippo#84

## 1. Whole-set dry-run validation (increment 1)

- [x] 1.1 `BatchValidationResult` dataclass added to
  `hippo/core/validation/validators.py` (overall `is_valid`/`passed`, ordered
  per-entity `results`, aggregated `failures`/`errors`, `invalid_results()`,
  `to_envelope()`), exported from `hippo.core.validation`.
- [x] 1.2 `HippoClient.validate_batch(operations, *, assign_ids=True)` runs the
  standard per-entity pipeline over each operation and aggregates (not
  fail-fast); assigns in-memory provisional ids on copies (caller data never
  mutated); performs no writes.
- [x] 1.3 Tests (`tests/core/test_validate_batch.py`): result-type unit tests;
  all-valid set; mixed set aggregates (not fail-fast); provisional id assigned +
  caller data untouched; no writes occur (storage asserted empty);
  `assign_ids=False` leaves id absent; empty set is valid.
- [x] 1.4 Existing validation/client/pipeline suites stay green.

## 2. Atomic multi-entity write (increment 2 — landed)

- [x] 2.1 `BatchWriteResult` dataclass added to
  `hippo/core/validation/validators.py` (`committed`/`dry_run` flags, the
  whole-set `validation`, per-entity `entities`, created `relationships`),
  exported from `hippo.core.validation`.
- [x] 2.2 `HippoClient.batch_put(operations, *, relationships=None,
  dry_run=False)`: assign real ids up front on copies (caller data untouched) →
  `validate_batch(assign_ids=False)` → on invalid, return without writing → on
  `dry_run`, return the plan without writing → else wrap all entity writes (then
  relationships) in one `self.staged_transaction()`; any exception rolls the
  whole set back and propagates.
- [x] 2.3 Relationships created **after** all entity writes within the same
  staged scope. No relaxation of `relate()`'s pre-existence check was needed:
  staged reads observe staged writes, so a relationship to a batch-member
  created earlier in the same transaction resolves naturally.
- [x] 2.4 Postgres adapter parity — `staged_transaction()` is present on the
  Postgres adapter and `batch_put` is backend-agnostic (delegates via
  `client.staged_transaction()`). Postgres-bound `batch_put` tests added in
  `tests/integration/test_postgres_adapter.py` (`TestPostgresBatchPut`: atomic
  commit, mid-batch rollback, intra-batch relationship); run by the
  `hippo-postgres` CI job (skipped locally without `HIPPO_DATABASE_URL`).
- [x] 2.5 Tests (`tests/core/test_batch_put.py`): atomic commit of a valid set;
  invalid set writes nothing; dry-run validates but writes nothing;
  rollback-on-mid-batch-failure leaves no partial writes; intra-batch
  relationship forward-reference resolves; relationship-to-missing-target rolls
  back the entities; id assigned without mutating caller data. Guard
  (`SDK_RESERVED_NAMES`) updated for `batch_put`.

## 3. Transport exposure (increment 3 — landed)

- [x] 3.1 REST `POST /ingest/batch` (atomic write) and `POST /ingest/validate`
  (whole-set dry-run), thin wrappers over `batch_put`/`validate_batch` in
  `serve/routers/ingest.py`. Validation failure → 422 with the structured body;
  dry-run → 200 with the plan.
- [x] 3.2 GraphQL root mutations `ingestBatch(entities, relationships, dryRun)`
  and `validateBatch(entities)` in `graphql/resolvers.py`, with
  `BatchEntityInput`/`BatchRelationshipInput` inputs and
  `BatchWriteGraphQLResult`/`BatchValidationGraphQLResult` types.
- [x] 3.3 Per-entity failure rendering: REST via `to_envelope`; GraphQL via the
  `BatchEntityValidation`/`ValidationFailureType` (tier-annotated) types.
- [x] 3.4 Tests: `tests/serve/test_ingest_batch.py` (REST: auth, missing
  entities, commit, dry-run, invalid→422 via a pre-write validator,
  relationship) and `tests/graphql/test_batch.py` (valid-set validate,
  commit, dry-run, write-time-constraint rollback, relationship).

## 4. Docs

- [x] 4.1 design/sec5 §5.4 carries a "batch unit-of-work (issue #84)" note
  (added with increment 1) generalizing the deferred `--atomic` flag.
