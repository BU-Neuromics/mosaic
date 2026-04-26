# Tasks — `typed-client`

## 1. Declare `hippo_accessor` and `hippo_namespace` in `hippo_ext`

- [x] 1.1 `hippo_accessor`: class-level string annotation. Range `string`; applies to classes; documented in `hippo_ext.yaml`.
- [x] 1.2 `hippo_namespace`: class-level string annotation added (supports Decision 9.8.B — namespace strings with dot-notation nesting). `root` is rejected as a value at load.
- [x] 1.3 `hippo_ext` version bumped 0.2.0 → 0.3.0.
- [x] 1.4 `linkml_bridge` exports the new `HIPPO_ACCESSOR` and `HIPPO_NAMESPACE` constants.

## 2. Pydantic generation at `SchemaRegistry` load time

- [x] 2.1 `hippo.core.typed_client.generate_pydantic_models(registry)` runs `linkml.generators.pydanticgen.PydanticGenerator` against a flattened merged schema and returns a `dict[class_name, BaseModel-subclass]`. In-memory; no file artifacts.
- [x] 2.2 Generation failures degrade gracefully with a `logger.warning` — accessors still work against plain dicts (Decision 9.8.H). Four failure points each have their own warning: generator import, serialization, Pydantic import, exec.
- [ ] 2.3 `hippo.models` module entry point exposing the generated classes under sub-modules per namespace (`hippo.models.tissue`, `hippo.models.assay.quant`) — **deferred**. The generated classes are attached to typed accessors via `EntityAccessor.model_class`; a separate `hippo.models` import surface is a later ergonomics pass.

## 3. Namespace-aware accessors

- [x] 3.1 Root-namespace classes flat on `HippoClient` (`client.samples.create(...)`) AND via `client.root.samples.create(...)` — both resolve to the same accessor (Decision 9.8.B).
- [x] 3.2 Non-root classes reachable via `client.<ns>.<accessor>` (e.g. `client.tissue.samples.create(...)`).
- [x] 3.3 Nested namespaces via dot notation — `hippo_namespace: assay.quant` produces `client.assay.quant.measurements.create(...)`. Intermediate containers (`client.assay` with only the `.quant` sub-namespace) are legal.
- [x] 3.4 Default accessor: `snake_case(ClassName) + "s"` — handles acronym boundaries (`DNASample` → `dna_samples`).
- [x] 3.5 `hippo_accessor` overrides the default.

## 4. Collision detection at schema load

All four cases raise ``TypedClientError`` at ``HippoClient.__init__`` with a
``.case`` field identifying which case fired.

- [x] 4.1 **Case 1** — same-namespace accessor duplication. `case == "duplicate_accessor"`.
- [x] 4.2 **Case 2** — class accessor vs. sub-namespace segment. `case == "accessor_vs_namespace"`.
- [x] 4.3 **Case 3** — namespace name vs. SDK-reserved (`query`, `root`, `storage`, …). `case == "namespace_reserved"` or `"reserved_root"`.
- [x] 4.4 **Case 4** — accessor vs. SDK-reserved name. `case == "accessor_reserved"`.

## 5. Coequal surface

- [x] 5.1 `.create`, `.get`, `.query`, `.put`, `.replace`, `.delete`, `.history`, `.state_at` all available on `EntityAccessor` and forward to the generic `HippoClient` path (Decision 9.8.D). `delete()` routes through `HippoClient.delete` so SDK-level hooks fire.
- [x] 5.2 Round-trip parity verified (`TestGenericTypedParity`).

## 6. ValidationFailed integration

- [x] 6.1 Typed-client write methods raise `ValidationFailed` carrying the envelope. `EntityAccessor._validate_or_raise()` runs `client.validate()` before storage; empty data is also rejected uniformly. `bypass_validation=True` prevents double-validation in the underlying client. `ValidationFailure` (legacy) remains for direct `HippoClient` callers per Decision 9.9.E.

## 7. Infrastructure classes excluded

- [x] 7.1 `hippo_core` primitives (`Entity`, `ProvenanceRecord`, `Process`, `Validator`, `ReferenceLoader`) are NOT exposed as typed accessors — system concerns.

## 8. Tests

- [x] 8.1 Default accessor derivation (4 cases).
- [x] 8.2 Root access — flat + `root` alias + write-through.
- [x] 8.3 Non-root namespaces — single-level, nested, empty-parent-container.
- [x] 8.4 `hippo_accessor` override.
- [x] 8.5 All four collision cases.
- [x] 8.6 Infrastructure classes excluded.
- [x] 8.7 Pydantic model attachment when generation succeeds.
- [x] 8.8 Generic/typed write-read parity.
- [x] 8.9 No-registry path.

## 9. Documentation

- [x] 9.1 Reference doc for typed-client access patterns. `docs/reference_typed_client.md` covers accessor API, Pydantic model access, namespace-aware patterns, and error handling.
- [x] 9.2 Decision 9.8.H logged.

## 10. Acceptance

- [x] 10.1 Pydantic classes generated at load time and attached to accessors.
- [x] 10.2 Namespace-aware accessors work for root (flat + explicit), non-root, and nested.
- [x] 10.3 Every generic call has a typed equivalent; every typed call works.
- [x] 10.4 Collision detection catches all four cases with actionable errors.
- [x] 10.5 `hippo_accessor` and `hippo_namespace` declared in `hippo_ext` and documented.
- [x] 10.6 Full suite green (897 passed, 7 skipped — +23 new typed-client tests).
