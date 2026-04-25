# Tasks — `reference-loader-shape`

## 1. Resolve design questions

- [x] 1.1 Multi-class loaders: `entity_type` is `multivalued: true` over `range: string`, declarative-only (provenance + discoverability); loader code owns runtime ingestion order; per-class metadata not modeled. Logged as Decision 9.5.F in `design/sec9_decisions.md` (PTS-67).
- [x] 1.2 `schema_fragment` load-order: fragment merges at plugin registration; ReferenceLoader instance validates against the merged SchemaView immediately after; either failure aborts plugin registration with a single error path. Logged as Decision 9.5.E in `design/sec9_decisions.md` (PTS-67).

## 2. Finalize `hippo_core` declaration

- [ ] 2.1 Update `ReferenceLoader` in `src/hippo/schemas/hippo_core.yaml` with the full slot inventory (name, entity_type multivalued, source, schema_fragment, plus any others from §1.1).
- [ ] 2.2 Bump `hippo_core` minor version.
- [ ] 2.3 Validate via `linkml-validate`.

## 3. Migrate existing loaders

- [ ] 3.1 Audit plugins registered under the `hippo.reference_loaders` entry point.
- [ ] 3.2 Update each to emit a `ReferenceLoader` instance matching the finalized shape.
- [ ] 3.3 Run the full test suite for reference loaders.

## 4. Introspection

- [ ] 4.1 `SchemaRegistry` exposes `reference_loaders()` returning the list of registered loaders.
- [ ] 4.2 Optional REST endpoint (gated by `generated-rest-surface` scope): `GET /schemas/reference_loaders`.

## 5. Documentation

- [ ] 5.1 Update `design/reference_hippo_core.md` `ReferenceLoader` section from placeholder to the finalized inventory.
- [x] 5.2 Logged the two design resolutions in `sec9_decisions.md` as Decision 9.5.E (fragment merge timing) and Decision 9.5.F (entity_type semantics).
- [ ] 5.3 ReferenceLoader developer documentation must explicitly call out the developer's responsibility for correct data-loading semantics — schema-side validation does not enforce ingestion order or FK satisfaction; the loader's own code owns it. (Per Decision 9.5.F.)

## 6. Acceptance

- [ ] 6.1 `ReferenceLoader` has a committed slot inventory in `hippo_core.yaml`.
- [ ] 6.2 Existing loaders pass under the new shape.
- [ ] 6.3 Full suite green.
