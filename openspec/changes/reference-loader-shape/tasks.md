# Tasks — `reference-loader-shape`

## 1. Resolve design questions

- [ ] 1.1 Multi-class loaders: finalize `entity_type` as multivalued; decide cardinality semantics (set vs. ordered); decide whether per-class metadata is carried alongside or in separate records. Document decision in `sec9_decisions.md`.
- [ ] 1.2 `schema_fragment` load-order: document the exact contract — when the fragment is merged into the SchemaView, when the ReferenceLoader instance is validated, the error surface. Document in `sec9_decisions.md`.

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
- [ ] 5.2 Log the two design resolutions in `sec9_decisions.md` as Decision 9.5.E and 9.5.F.

## 6. Acceptance

- [ ] 6.1 `ReferenceLoader` has a committed slot inventory in `hippo_core.yaml`.
- [ ] 6.2 Existing loaders pass under the new shape.
- [ ] 6.3 Full suite green.
