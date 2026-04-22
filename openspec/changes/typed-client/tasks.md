# Tasks — `typed-client`

## 1. Declare `hippo_accessor` in `hippo_ext`

- [ ] 1.1 Add `hippo_accessor` slot to `src/hippo/schemas/hippo_ext.yaml` with `range: string`, `in_subset: [class_annotation]`. No default (absence → derived accessor).
- [ ] 1.2 Document in `reference_hippo_ext.md`.
- [ ] 1.3 Bump `hippo_ext` minor version.

## 2. Pydantic generation

- [ ] 2.1 At `SchemaRegistry` load time, run LinkML's `PythonGenerator` against the flattened (merged) SchemaView.
- [ ] 2.2 Expose generated classes under `hippo.models` with per-namespace sub-modules mirroring the schema namespace structure (e.g. `hippo.models.tissue`, `hippo.models.assay.quant`).
- [ ] 2.3 Generation is in-memory; the module is rebuilt on schema reload.

## 3. Namespace-aware accessors

- [ ] 3.1 Build the client accessor tree from the merged SchemaView:
  * Root-namespace classes → flat attributes on `client` and mirrored under `client.root`.
  * Non-root namespaces → attributes on `client.<namespace>` with dot-notation splitting.
- [ ] 3.2 Each accessor (`client.samples`) exposes `create`, `get`, `update`, `supersede`, `query` matching the generic client surface.
- [ ] 3.3 Accessor names default to `snake_case(ClassName) + "s"`; `hippo_accessor` overrides.

## 4. Collision detection

- [ ] 4.1 At schema load, compute every expected attribute on `client` and every nested namespace.
- [ ] 4.2 Check four collision cases (per sec9 §9.8): same-namespace duplicate accessor, class accessor vs sub-namespace segment, namespace name vs SDK-reserved attribute, accessor vs SDK-reserved name.
- [ ] 4.3 Each case produces a distinct error template naming the offending elements and suggesting the `hippo_accessor` fix.

## 5. Coequal surfaces

- [ ] 5.1 Typed accessors delegate to the same SDK internals — no duplicate code path.
- [ ] 5.2 Integration tests pair each typed call with the generic equivalent and assert both succeed.

## 6. Validation integration

- [ ] 6.1 Typed write paths call the unified validation pipeline (post `validation-tiering-clarification`).
- [ ] 6.2 Validation failures raise `ValidationFailed` with the envelope.
- [ ] 6.3 Pydantic's own type checks run BEFORE the SDK validation pipeline (construction-time LinkML-native shape).

## 7. Tests

- [ ] 7.1 `client.samples.create(Sample(...))` round-trips a root-namespace class.
- [ ] 7.2 `client.root.samples.create(...)` equivalent to the flat form.
- [ ] 7.3 `client.tissue.samples.create(Sample(...))` round-trips a tissue-namespace class.
- [ ] 7.4 Nested namespace access: `client.assay.quant.measurements.create(...)`.
- [ ] 7.5 `hippo_accessor` override: class with `hippo_accessor: custom_samples` is reachable via `client.custom_samples`.
- [ ] 7.6 Four collision cases each fail at schema load with the documented error template.
- [ ] 7.7 Pre-load autocomplete (optional) if static generation is implemented.

## 8. Documentation

- [ ] 8.1 Update `design/reference_hippo_core.md` with a note on typed-client access for each class.
- [ ] 8.2 Update `design/reference_hippo_ext.md` with `hippo_accessor`.
- [ ] 8.3 Log opinionated implementation calls in `sec9_decisions.md`.

## 9. Acceptance

- [ ] 9.1 Pydantic classes generated and reachable under `hippo.models`.
- [ ] 9.2 Namespace-aware accessors work for all four access patterns.
- [ ] 9.3 Collision detection covers all four cases.
- [ ] 9.4 Every generic call has a typed equivalent; every typed call works.
- [ ] 9.5 Full suite green.
