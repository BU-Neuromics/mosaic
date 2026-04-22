# Validation Tiering Clarification

## Why

Per sec9 §9.9, Hippo runs three tiers of validation — LinkML-native
(static shape), CEL (dynamic / cross-entity), and Python plugin
(everything else). The behavior exists today, but it's not formalized:
failures from different tiers take different shapes, the REST surface
returns inconsistent errors, and the "which tier does this rule belong
to?" question has no authoritative answer for coding agents. This change
formalizes the contract.

## What Changes

### Fixed-order three-tier pipeline

1. LinkML-native — types, patterns, enums, ranges, required, multivalued, unique_keys.
2. CEL — boolean expressions over entity data with optional `expand`
   pre-fetching.
3. Python plugin — escape hatch for things neither tier can express.

Execution: cheapest first, fail-fast by default, opt-in collect-all for
batch ingest.

### Unified `ValidationResult` envelope

```
ValidationResult:
  passed: bool
  failures: list[ValidationFailure]

ValidationFailure:
  tier: Literal["linkml", "cel", "python"]
  rule: str
  field: Optional[str]
  message: str
  details: dict
```

All three tiers return this shape.

### REST error mapping

REST responses map `ValidationResult` to HTTP 400/422 with a structured
body carrying the failure list. Typed client raises `ValidationFailed`
carrying the envelope.

### Boundary rules

Documented in `reference_validators_yaml.md`:

- If LinkML can express it, it MUST be in LinkML.
- If CEL can express it (pure function over entity data with expand
  pre-fetching), it MUST be in CEL.
- Python plugins only for things neither can express.

## Capabilities

### New Capabilities

- `validation-tiering-contract` — explicit three-tier pipeline with
  unified result envelope.

### Modified Capabilities

- `hippo-validation` — consistent envelope across tiers.
- `rest-error-mapping` — structured HTTP 400/422.
- `typed-client` — raises ValidationFailed with the envelope.

## Dependencies

- **Soft-blocked by:** `computed-temporal-fields` (not a hard dep; can
  land in parallel).
- **Blocks:** `typed-client` (it consumes the envelope).

## Acceptance

- Every validation failure reports its tier.
- REST 400/422 responses contain the structured body.
- Existing CEL and Python validators continue to run unchanged; only the
  result shape and reporting are unified.
- `reference_validators_yaml.md` documents the boundary rules.
- Full suite green.
