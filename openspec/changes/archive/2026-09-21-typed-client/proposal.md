# Typed Client

## Why

sec9 §9.8 introduces a Pydantic-generated typed client alongside the
existing generic `HippoClient`. Users get `client.samples.create(Sample(...))`
with IDE autocomplete and static type checking, while the dynamic
`HippoClient.create("Sample", {...})` path stays fully supported. The
typed client mirrors the schema's namespace structure with dual root
access and nested-namespace support via dot notation.

Also declares the `hippo_accessor` annotation in `hippo_ext` alongside
its consumer (Decision 9.4.B).

## What Changes

### Declare `hippo_accessor` in `hippo_ext`

- New class-level string annotation; optional escape hatch when the
  default accessor derivation (`snake_case(ClassName) + "s"`) produces a
  collision or a deployment wants a non-default name.

### Pydantic generation at `SchemaRegistry` load time

- LinkML's `PythonGenerator` (aka `gen-pydantic`) runs against the merged
  SchemaView at load time.
- In-memory generation; exposed under a stable SDK entry point (e.g.
  `hippo.models`, with sub-modules per namespace: `hippo.models.tissue`,
  `hippo.models.assay.quant`).
- No file artifacts by default; static file generation is a possible
  future supplement for pre-load IDE autocomplete.

### Namespace-aware accessors

Per sec9 §9.8:

- Root-namespace classes: flat (`client.samples.create(...)`) and
  explicit (`client.root.samples.create(...)`); `client.root` is an alias.
- Non-root namespaces: `client.tissue.samples.create(...)`.
- Nested via dot notation: `namespace: assay.quant` produces
  `client.assay.quant.samples.create(...)`.
- Accessor default: `snake_case(ClassName) + "s"`. `hippo_accessor`
  overrides per class.

### Collision detection at schema load

Four cases fail loudly with actionable error templates:

1. Same-namespace accessor duplication.
2. Class accessor vs. sub-namespace segment.
3. Namespace name vs. SDK-reserved attribute.
4. Accessor vs. SDK-reserved name.

### Coequal surfaces

Every SDK capability reachable from both the typed client and the
generic `HippoClient`. A feature that only exists in one is a defect.
Writes from both paths go through the same validation pipeline (from
`validation-tiering-clarification`).

## Capabilities

### New Capabilities

- `typed-client` — Pydantic-generated typed access surface.
- `hippo_accessor-annotation` — optional accessor-name override.

### Modified Capabilities

- `hippo-client-api` — gains the typed accessors.
- `hippo-ext-vocabulary` — gains `hippo_accessor`.

## Dependencies

- **Blocked by:** `validation-tiering-clarification` (recommended —
  error-surface parity).
- **Blocks:** `generated-rest-surface` (optional, deferred).

## Acceptance

- Pydantic classes generated at load time under `hippo.models`.
- Namespace-aware accessors work for root (flat + explicit) and non-root
  (including nested namespaces).
- Every generic call has a typed equivalent; every typed call works.
- Collision detection catches all four cases with actionable errors.
- `hippo_accessor` declared in `hippo_ext` and documented.
- Full suite green.
