# Tasks — `validation-tiering-clarification`

## 1. Unified envelope

- [ ] 1.1 Define `ValidationResult` and `ValidationFailure` dataclasses with `tier` annotation.
- [ ] 1.2 Migrate LinkML-native validation output to the envelope (one failure per LinkML validation error).
- [ ] 1.3 Migrate CEL validator output (CEL validator already has close-to-envelope shape; align field names).
- [ ] 1.4 Migrate Python plugin output; update plugin ABC to return `ValidationResult`.

## 2. Fixed order + fail-fast

- [ ] 2.1 Pipeline runs LinkML → CEL → Python in order.
- [ ] 2.2 Fail-fast default; opt-in `collect_all=True` for batch ingest.

## 3. REST error mapping

- [ ] 3.1 FastAPI exception handler maps `ValidationResult` / `ValidationFailed` to HTTP 400/422 with structured JSON body.
- [ ] 3.2 Response schema includes: `passed`, `failures[].tier`, `failures[].rule`, `failures[].field`, `failures[].message`.

## 4. Typed client exception

- [ ] 4.1 `ValidationFailed` exception carrying the envelope.
- [ ] 4.2 Raised by typed-client write methods when validation fails.

## 5. Documentation

- [ ] 5.1 Update `design/reference_validators_yaml.md` with the boundary rules and envelope shape.
- [ ] 5.2 Log opinionated implementation calls in `sec9_decisions.md`.

## 6. Tests

- [ ] 6.1 Each tier's failures render as the unified envelope with correct `tier` annotation.
- [ ] 6.2 Fail-fast mode stops after the first failing tier.
- [ ] 6.3 Collect-all mode aggregates across tiers.
- [ ] 6.4 REST returns structured 400/422.
- [ ] 6.5 Typed-client raises `ValidationFailed` with the envelope.

## 7. Acceptance

- [ ] 7.1 Unified envelope everywhere; no tier-specific error shapes remain.
- [ ] 7.2 REST structured errors.
- [ ] 7.3 Full suite green.
