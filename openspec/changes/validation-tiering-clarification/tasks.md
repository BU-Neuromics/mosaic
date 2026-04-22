# Tasks — `validation-tiering-clarification`

## 1. Unified envelope

- [x] 1.1 `ValidationFailure` dataclass in `hippo.core.validation.validators` with `tier`, `rule`, `message`, optional `field`, `details` dict. `Tier = Literal["linkml", "cel", "python"]`.
- [x] 1.2 `ValidationResult` extended with `failures: list[ValidationFailure]` (sec9 envelope). `__post_init__` reconciles the legacy `errors: list[str]` view and the new `failures` view so callers from either era continue to work (Decision 9.9.D). Legacy callers get `failures` with `tier="python"` / `rule="legacy"` synthesized.
- [x] 1.3 LinkML-native tier: `SchemaRegistry.validate_envelope(instance, target_class)` returns `list[ValidationFailure]` with `tier="linkml"` for every LinkML validation error. The legacy `.validate()` string-list path is preserved for back-compat.
- [x] 1.4 `WriteValidator.tier` property added (defaults to `"python"`); plugin ABC still returns `ValidationResult`, which now carries tier-annotated failures.

## 2. Fixed order + fail-fast

- [x] 2.1 The pipeline already runs validators in priority order with fail-fast default (pre-existing `ValidationPipeline.execute`). Tier ordering is the natural consequence of prioritizing LinkML validators highest, then CEL, then Python. Deployment-specific ordering is enforceable via `WriteValidator.priority`.
- [x] 2.2 `execute_all()` on the pipeline aggregates failures across tiers for batch/collect-all paths.

## 3. REST error mapping

- [x] 3.1 FastAPI exception handler for `ValidationFailed` added in `hippo/api/factory.py`. Maps to HTTP 422 with a structured body including `passed`, `failures[].tier`, `failures[].rule`, `failures[].field`, `failures[].message`, `failures[].details`.
- [x] 3.2 `ValidationResult.to_envelope()` renders the REST body shape.

## 4. Typed client exception

- [x] 4.1 `hippo.core.exceptions.ValidationFailed` added (Decision 9.9.E — new exception, coexists with the existing `ValidationFailure` exception to avoid a rename cascade). Carries the full envelope via `.result`.
- [ ] 4.2 Raised by typed-client write methods when validation fails — **deferred to the `typed-client` change** that follows. The exception class is available now; the typed-client integration arrives with its consumer.

## 5. Documentation

- [x] 5.1 `design/reference_validators_yaml.md` prepended with the sec9 §9.9 three-tier pipeline section — tier definitions, boundary rules, envelope shape, REST mapping. The existing CEL-tier file format reference is unchanged.
- [x] 5.2 Decisions 9.9.D (back-compat envelope extension) and 9.9.E (`ValidationFailed` vs. existing `ValidationFailure` exception naming) logged in `sec9_decisions.md`.

## 6. Tests

- [x] 6.1 Each tier's failures render as the unified envelope with correct `tier` annotation (`test_validation_tiering.py::TestLinkmlValidateEnvelope`, `::TestPipelineAggregation`).
- [x] 6.2 Fail-fast mode stops after the first failing tier — transitively covered by existing pipeline tests in `test_validation.py`.
- [x] 6.3 Collect-all mode aggregates across tiers — `TestPipelineAggregation::test_aggregated_failures_preserve_tier_tags`.
- [ ] 6.4 REST returns structured 422 — **deferred**. The handler is wired up; a full FastAPI integration test that exercises the path lands with the typed-client change.
- [x] 6.5 `ValidationFailed` carries the envelope (`TestValidationFailedException`).

## 7. Acceptance

- [x] 7.1 Unified envelope available everywhere (every `ValidationResult` now carries `.failures`). Legacy tier-specific error shapes still render via `.errors` for callers that haven't migrated.
- [x] 7.2 REST structured-error handler registered for `ValidationFailed`.
- [x] 7.3 Full suite green (874 passed, 7 skipped — 10 new tiering tests added).
