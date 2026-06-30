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

## 2. Atomic multi-entity write (increment 2 — planned)

- [ ] 2.1 `BatchWriteResult` type (per-entity created/updated id + status, or
  per-entity failure).
- [ ] 2.2 `HippoClient.batch_put(operations, dry_run=False)`: assign ids up front
  → resolve intra-batch references → `validate_batch` → if valid and not
  `dry_run`, wrap all writes in a single `staged_transaction()`; rollback on any
  failure.
- [ ] 2.3 Defer relationship-edge creation until after entity writes within the
  same transaction so intra-batch forward references resolve (relax the
  `relate()` pre-existence check for batch-local targets).
- [ ] 2.4 Postgres adapter parity (`staged_transaction()` already present).
- [ ] 2.5 Tests: atomic commit of a valid set; rollback-on-failure leaves no
  partial writes / no orphan provenance; intra-batch forward reference resolves.

## 3. Transport exposure (increment 3 — planned)

- [ ] 3.1 REST `POST /ingest/batch` (thin wrapper over `batch_put`/`validate_batch`).
- [ ] 3.2 GraphQL `ingestBatch(entities, dryRun)` mutation.
- [ ] 3.3 Per-entity failure rendering in the sec9 §9.9 envelope shape.

## 4. Docs

- [ ] 4.1 Note the batch unit-of-work in design/sec5 (supersedes the deferred
  `--atomic` note in §5.4) once increment 2 lands.
