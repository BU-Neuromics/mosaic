# Hippo — Metadata Tracking Service
## Specification Index

**Codename:** Hippo  
**Component:** Metadata Tracking Service (MTS)  
**Version:** 0.1 — Implementation Ready  
**Status:** Ready for implementation  
**LinkML-centric redesign:** Approved 2026-04-18. See `sec9_linkml_redesign.md` (authoritative design) and `sec9_decisions.md` (drafting decision log). Pre-redesign state preserved at git tag `design-pre-linkml`. Section revisions land coordinated with each OpenSpec change per 9.12.

---

## Document Map

| File | Section | Status | Notes |
|---|---|---|---|
| `sec1_overview.md` | 1. Overview & Scope | ✅ Draft v0.1 | Domain-neutral; no deployment-specific types |
| `sec2_architecture.md` | 2. Architecture | ✅ Draft v0.1 | SDK-first layering, all plugin ABCs, validation infrastructure, search |
| `sec3_data_model.md` | 3. Data Model | ✅ Draft v0.1 | Polymorphic inheritance, search field declarations, `requires:` block |
| `sec3b_relational_storage.md` | 3b. Relational Storage Mapping | ✅ Draft v0.1 | SQLite/PostgreSQL reference impl; §3b.8 polymorphic storage |
| `sec4_api_layer.md` | 4. API Layer | ✅ Draft v0.1 | HippoClient interface, REST endpoints, pagination, polling |
| `sec5_ingestion.md` | 5. Ingestion & Integration | ✅ Draft v0.1 | Flat-file, reference data, upsert-by-ExternalID, error handling |
| `sec6_provenance.md` | 6. Provenance & Audit | ✅ Draft v0.1 | Event model, structured context, storage, history API, retention |
| `sec7_nfr.md` | 7. Non-Functional Requirements | ✅ Draft v0.1 | Performance targets, scalability tiers, reliability, schema sync roadmap |
| `sec8_auth_integration.md` | 8. Authentication & Authorization Integration | ✅ Draft v0.1 | Bridge-aware `AuthMiddleware` impl, actor propagation, audit trail split |
| `sec9_linkml_redesign.md` | 9. LinkML-Centric Redesign | ✅ Approved 2026-04-18 | Three-layer schema stack, first-class `Process`, PROV-O-aligned `ProvenanceRecord`, UUID identity model, namespace-aware typed client |
| `sec9_decisions.md` | 9. (Companion) Decisions Log | ✅ Approved 2026-04-18 | Drafting decisions with alternatives, rationale, revert paths |
| `appendix_a_example_schema_omics.md` | Appendix A. Example Schema (Omics) | ✅ Draft v0.1 | Complete LinkML schema with `search:`, polymorphic extension example |
| `appendix_b_implementation_guide.md` | Appendix B. Implementation Guide | ✅ Draft v0.1 | Build order, module map, error hierarchy, invariants, test strategy, OpenSpec mapping |
| `reference_hippo_yaml.md` | Reference: `hippo.yaml` Config Schema | ✅ Draft v0.1 | All valid keys, types, defaults, env var substitution, minimal configs |
| `reference_validators_yaml.md` | Reference: `validators.yaml` Format | ✅ Draft v0.1 | Complete field spec, expand syntax, all built-in presets, execution semantics |
| `reference_cel_context.md` | Reference: CEL Evaluation Context | ✅ Draft v0.1 | All context variables, CEL types, expanded field shapes, available functions, common patterns |

---

## LinkML-Centric Redesign (Approved — Implementation Underway)

**Status:** Approved 2026-04-18. `sec9_linkml_redesign.md` is the authoritative design; `sec9_decisions.md` captures drafting decisions. This block is the high-level treatment plan; specific design claims are owned by sec9. Section revisions land coordinated with each OpenSpec change (see sec9 §9.12).

### Motivation

Recent refactors (`delete SchemaParser/SchemaConfig/FieldDefinition`, `swap DDL/migration/diff to SchemaRegistry`, `feat: LinkML-backed SchemaRegistry seam`) have been unwinding a pre-LinkML schema-abstraction layer. This proposal completes the direction by making LinkML the spine of Hippo: a three-layer schema stack (extension vocabulary → Hippo core schema → user schema) with `Entity` and `ProvenanceRecord` modeled as first-class LinkML classes rather than hand-coded Python constructs.

### New Artifacts

| File | Purpose |
|---|---|
| `sec9_linkml_redesign.md` | Vision doc — three-layer stack, provenance-as-LinkML-class, migration narrative, tradeoffs |
| `reference_hippo_core.md` | Reference for `hippo_core.yaml` (Entity, ProvenanceRecord, Status/Operation enums, Validator) |
| `reference_hippo_ext.md` | Reference for `hippo_ext.yaml` — the `hippo_*` annotation vocabulary (`hippo_unique`, `hippo_index`, `hippo_index_partial`, `hippo_search`, `hippo_append_only`, `hippo_accessor`) |

### Per-Section Revision Plan

Legend: 🟢 Light touch • 🟡 Moderate • 🔴 Major rewrite

| Section | Treatment | Reason |
|---|---|---|
| sec1 Overview | 🟢 | Purpose/scope domain-neutral; touch only paragraphs citing removed `SchemaConfig`/`SchemaLoader` |
| sec2 Architecture | 🟢 | Three-layer SDK-first reinforced, not changed; update `SchemaRegistry` seam and entry-point list |
| sec3 Data Model | 🔴 | Conceptual model recast on LinkML primitives; `base:` polymorphic inheritance mapped onto `is_a`; namespace semantics reconciled with LinkML schema-level namespacing |
| sec3b Relational Storage | 🔴 | DDL generation path fully LinkML-driven; polymorphic storage semantics revisited; partial-index annotations formalized |
| sec4 API Layer | 🟡 | Typed (Pydantic-generated) client added alongside generic `HippoClient`; generated REST surface noted as roadmap; core interfaces stable |
| sec5 Ingestion | 🟡 | Validation pipeline largely unchanged; reference-loader ABC reshaped around a LinkML-declared `ReferenceLoader` class |
| sec6 Provenance & Audit | 🔴 | `ProvenanceRecord` becomes a LinkML class with a DDL-generated table; temporal fields formalized as computed reads/views |
| sec7 NFR | 🟢 | Targets unchanged; schema-sync roadmap revisited if REST surface becomes generated |
| sec8 Auth Integration | 🟢 | Orthogonal to schema design; no change expected |
| Appendix A Example Schema (Omics) | 🟡 | Rework to `import: hippo_core`; demonstrate `is_a: Entity` on domain classes |
| Appendix B Implementation Guide | 🔴 | Build order, module map, invariants, test strategy all shift |
| `reference_hippo_yaml.md` | 🟢 | May gain `hippo_core_path` / extension-import config |
| `reference_validators_yaml.md` | 🟡 | Clarify division between LinkML-native validation (types/patterns/enums/ranges) and CEL (cross-entity/dynamic rules) |
| `reference_cel_context.md` | 🟢 | Context shape unchanged |

### Preservation of Historical Design

- **Git tag** `design-pre-linkml` applied to current HEAD before any section rewrite begins. `git checkout design-pre-linkml -- design/` always recovers the prior spec.
- Major-rewrite sections preserved as `secN_pre_linkml.md` alongside new versions during the transition, removed once sec9 is merged and the OpenSpec changes have landed.
- Superseded entries in the Key Decisions Log are not deleted — they gain a `Superseded by` pointer into sec9.

### Decision-Log Impact (Preview)

Existing decisions expected to be reaffirmed / reformulated (non-exhaustive, to be finalized in sec9):

- *Data model approach* — reaffirmed; expressed via LinkML classes + `hippo_ext` annotations instead of config keys
- *Temporal metadata: provenance-log only, computed at read time* — reaffirmed and formalized as views over a DDL-generated provenance table
- *Schema authoring: direct LinkML* — reaffirmed and extended to Hippo's own core schema
- *Namespace* decisions (inference, root canonicalization, backwards compatibility) — reconciled with LinkML schema-level namespacing; treatment deferred to sec9

New decisions to be introduced in sec9 (preview):

- Three-layer schema stack: `hippo_ext` → `hippo_core` → user schema
- `ProvenanceRecord` is a first-class LinkML class; its table is DDL-generated via the same path as entity tables
- `hippo_*` annotations formalized as a versioned LinkML extension vocabulary
- Typed Pydantic-generated client available alongside generic `HippoClient`

### Progress

1. ~~Review and approve this block~~ — **Approved 2026-04-18**.
2. ~~Tag `design-pre-linkml` on current HEAD~~ — **Applied 2026-04-18**.
3. ~~Draft `sec9_linkml_redesign.md` via the `doc-coauthoring` workflow~~ — **Complete**; see `sec9_linkml_redesign.md` and `sec9_decisions.md`.
4. **In progress.** Decompose into OpenSpec changes per sec9 §9.12. Ten changes grouped into three waves (foundation / data-model / consumer-facing). Scaffolding Wave 1 first: `hippo-ext-vocabulary` → `hippo-core-schema` → `id-registry-and-uuid-strategy` → `process-class`.
5. **Pending.** Revise each section per the Revision Plan, coordinated with the OpenSpec change that triggers it.

---

## Key Decisions Log

| Decision | Choice | Section |
|---|---|---|
| Deployment model | SDK-first; REST and GraphQL are independent transport adapters | sec2 |
| Async strategy | Sync SDK for v0.1; revisit at PostgreSQL adapter | sec2 |
| REST deployment | Standalone (`hippo serve`) wrapping embedded `app` object | sec2 |
| Plugin system | Entry points (`hippo.storage_adapters`, `hippo.external_adapters`, `hippo.write_validators`, `hippo.reference_loaders`) | sec2 |
| Storage backend v0.1 | SQLite via stdlib `sqlite3` | sec2 |
| Data model approach | Config-driven relational + graph-shaped API; graph DB as future adapter | sec3 |
| Temporal metadata | Provenance log only — not stored on entities; computed at read time | sec3, sec6 |
| Entity lifecycle | `is_available` boolean; storage adapters optimize for this filter | sec3, sec3b |
| Lifecycle semantics | Reason for unavailability stored in provenance events, not on entities | sec3, sec6 |
| Supersession | System-level `superseded_by` relationship; atomic SDK operation | sec3 |
| Schema authoring | Direct LinkML (YAML/JSON) — no intermediate DSL or compilation step | sec3 |
| Graph DB | Future adapter option; not v0.1 scope | sec3 |
| Multi-tenancy | Out of scope for v0.1 | sec3 |
| Conceptual/storage separation | Sec3 defines conceptual data model only; relational storage mapping in sec3b | sec3, sec3b |
| Domain-neutral spec | System spec contains no domain-specific schema; omics types in Appendix A only | sec1, sec2, sec3 |
| Schema inheritance semantics | `base:` creates polymorphic (is-a) inheritance — subtypes are queryable as their parent type | sec3, sec3b |
| Validator `entity_types` matching | Subtype-aware — declaring a parent type covers all subtypes; redundant entries emit startup warning | sec2 |
| Config-driven validation | `validators.yaml` with CEL conditions, `expand` path pre-fetching, `when` pre-conditions, `requires` shorthand, `existing` context | sec2 |
| CEL expression language | Used for config-driven validator conditions; sandboxed, no I/O, `cel-python` binding | sec2 |
| Expand path syntax | `field`, `field.child`, `field[]`, `field[].child`; batch-fetched; cycle detection; `max_expand_list_size` cap | sec2 |
| Lazy evaluation rejected | Explicit `expand` paths preferred — CEL short-circuit makes implicit I/O non-deterministic | sec2 |
| Built-in validator presets | `ref_check`, `count_constraint`, `immutable_field`, `field_required_if`, `no_self_ref` as ergonomic shortcuts | sec2 |
| External adapter boundary | STARLIMS, HALO, REDCap concrete implementations in Cappella; `ExternalSourceAdapter` ABC stays in Hippo | sec2 |
| Reference loader plugin system | `hippo.reference_loaders` entry point; `ReferenceLoader` ABC ships `schema_fragment()`; install auto-migrates | sec2, sec5 |
| Fuzzy search | `EntityStore.search()` ABC method; per-field `search:` mode; `ScoredMatch` core SDK type; adapter capability declaration at startup | sec2, sec3, sec4 |
| Provenance event model | Typed events (EntityCreated/Updated/AvailabilityChanged/Superseded/Relationship*/ExternalId*/Migration*/ReferenceData*) | sec6 |
| Provenance context | Unstructured JSON `context` field on all events; Cappella conventions documented | sec6 |
| Batch ingestion semantics | Per-record transactions by default; `--fail-fast` flag; `--atomic` deferred | sec5 |
| Upsert identity resolution | Priority: explicit UUID → ExternalID lookup → new entity | sec5 |
| Pagination | Offset-based (limit/offset); cursor-based deferred | sec4 |
| Multi-instance REST | Fully stateless; all distributed concerns delegated to storage adapter | sec7 |
| Schema sync v0.1 | Restart-on-migrate; three-phase post-v0.1 roadmap documented | sec7 |
| Multi-instance adapter contract | Must implement atomic server-side upsert (not read-then-write) for entity and ExternalID creation | sec2, sec7 |
| Entity namespaces | Optional `namespace:` key in schema files scopes entities to named namespaces; FQN = `namespace.EntityType`; root namespace is the only implicit namespace | sec3 |
| NamespaceRegistry | Built by `SchemaLoader` at load time; maps `(namespace, entity_name)` → `EntityConfig`; fully populated before cross-namespace reference validation | sec3 |
| Namespace dependency inference | Dependencies inferred from `references.entity_type` FQNs — no explicit `depends_on:` required; topological sort detects cycles | sec3 |
| Root namespace canonicalization | `root.Donor` normalized to `"Donor"` at registry ingestion; only unqualified form in `SchemaConfig` and storage. **Superseded at the client level by sec9.8** — typed client provides dual access (flat `client.samples` and explicit `client.root.samples`); storage-level canonicalization unchanged | sec3, sec9 |
| Namespace backwards compatibility | Schemas without `namespace:` key load unchanged; no data migration required for existing deployments | sec3 |
| Provenance event model | Typed events (EntityCreated/Updated/AvailabilityChanged/Superseded/Relationship*/ExternalId*/Migration*/ReferenceData*). **Reshaped by sec9.6** — `ProvenanceRecord` is now a first-class LinkML class with PROV-O alignment (`class_uri: prov:Activity`); event categories expressed as the `Operation` enum in `hippo_core` (`create`, `update`, `availability_change`, `supersede`, `relationship_add`/`remove`, `external_id_add`/`remove`, `migration_applied`, `reference_data_installed`) | sec6, sec9 |
| Provenance-log-only temporal data | `created_at`, `updated_at`, `schema_version` never stored on entity tables; always computed from `ProvenanceRecord` at read time. **Formalized by sec9.7** — adds `created_by` and `updated_by` as computed fields; defines required indexes and batch aggregation primitives | sec3, sec6, sec9 |
| Three-layer schema stack | `hippo_ext` (annotation vocabulary) → `hippo_core` (Entity, ProvenanceRecord, Process, Validator, ReferenceLoader, Status/Operation enums) → user schema. Imports flow downward only. `SchemaRegistry` produces one merged `SchemaView` consumed by every subsystem | sec9.3 |
| `hippo_*` extension vocabulary | `hippo_ext` is a shipped-with-Hippo LinkML schema that declares every `hippo_*` annotation with `applies_to`, `value_type`, and `cardinality` constraints. Every used annotation MUST be declared; undeclared annotations fail at load time | sec9.4 |
| `Process` as first-class class | Composite activity grouping atomic `ProvenanceRecord` entries under one logical execution (reference loads, pipeline runs, schema migrations). `is_a: Entity`, `class_uri: prov:Activity`. Minimum slots: `parent_process_id`, `operation_kind`, `started_at`, `ended_at`, `actor_id` | sec9.5 |
| UUID identity model | Every `id` is a UUID, globally unique by collision probability. Polymorphic references carry a UUID alone. Type resolution: relational adapters maintain an `_entity_registry` table; Neo4j uses native labels | sec9.2, sec9.5 |
| FQN parsing rule | Fully qualified class name = `<namespace>.<ClassName>`. The last dot-separated segment is always the class name; everything before is the namespace string. Dots in class names are forbidden | sec9.5 |
| Provenance integrity transactional and loud | Entity mutation + `ProvenanceRecord` write are one atomic unit; either both land or neither does. Missing or inconsistent provenance at read time raises `ProvenanceIntegrityError` — no silent degradation | sec9.2, sec9.6 |
| Namespace-aware typed client | Root classes accessible via flat `client.<accessor>` or explicit `client.root.<accessor>`. Non-root via `client.<namespace>.<accessor>`. Nested namespaces via dot notation (e.g. `assay.quant`) produce nested attributes. Accessor default: `snake_case(ClassName) + "s"`; `hippo_accessor` overrides per class | sec9.8 |
| Validation tiering | Three tiers in fixed order: LinkML-native (static shape) → CEL (dynamic / cross-entity) → Python plugin (escape hatch). Fail-fast by default; opt-in collect-all for batch ingest. Unified `ValidationResult` envelope with tier annotation | sec9.9 |
| LinkML ecosystem adopted as-is | Hippo uses `SchemaView`, `gen-sqlddl`, `gen-pydantic`, `linkml-validate`, `linkml-diff` directly. Shims strictly bounded to applying `hippo_*` annotation effects. LinkML bugs fixed upstream or by version upgrade — never reimplemented in Hippo. Exact version pinning; LinkML patch bump triggers Hippo version bump | sec9.10 |

---

## Open Questions

Items requiring a future design decision before implementation. Deferred items are explicitly
out of scope for v0.1 and documented here for tracking.

| Question | Section | Priority | Status |
|---|---|---|---|
| Where does the example omics schema ultimately live? | — | Low | Open — config repo, `schemas/omics/`, or community `hippo-reference-omics` package |
| Entity type remapping / namespace migration path (OQ1) | sec3 §3.12 | High | Open — no migration path exists for moving `Sample` (root) to `tissue.Sample`; must be resolved before any production namespace adoption of existing entities. Options: `hippo migrate --remap`, namespace aliasing, or out-of-band migration script |
| Canonical form for root-namespace entities in storage (OQ2) | sec3 §3.11 | Low | Decided — store as `"Donor"` (unqualified); registry normalizes `root.*` to unqualified at load time. Client-side access revisited by sec9.8 (dual `client.samples` + `client.root.samples` paths); storage behavior unchanged |
| Ingestion idempotency for live webhook integrations | sec5 | High | Deferred — ExternalID upsert is the stable foundation; webhook retry deduplication needs a dedicated design session when live integrations are scoped |
| Explicit update endpoint (PUT, 404-on-missing) | sec4 | Medium | **Planned v0.5 (Phase 1)** — `PUT /entities/{type}/{id}`; partial update semantics, 404 if entity absent; specced in sec4 §4.3 |
| Bulk availability change endpoint | sec4 | Medium | **Planned v0.5 (Phase 1)** — `POST /entities/{type}/bulk-availability`; specced in sec4 §4.3 |
| OR filter composition in query API | sec4 | Low | **Planned v0.5 (Phase 1)** — multi-value params (same-field OR) + `?filter=` CEL (cross-field); specced in sec4 §4.3 |
| Per-validator timeout | sec2 | Low | Deferred — plugin validators should complete in <100ms; configurable timeout post-v0.1 |
| `hippo_poll` efficiency at scale | sec3b/sec6 | Medium | Deferred — provenance timestamp index handles current workload; denormalised `updated_at` column if needed at scale |
| Schema version check on writes (503 on mismatch) | sec7 | Medium | Planned for v0.2 — roadmap documented in sec7 §7.3 |
| Dynamic schema reload via polling | sec7 | Medium | Planned for v0.3 — roadmap documented in sec7 §7.3 |
| Expand-contract convention enforcement in `hippo migrate` | sec2/sec3 | Medium | Planned for v0.3+ — roadmap documented in sec7 §7.3 |
| Cursor-based pagination | sec4 | Low | **Planned v0.5 (Phase 1)** — cursor-based mode specced in sec4 §4.4; offset mode remains the default |
| GraphQL transport | sec2 | Low | Reserved in `hippo/graphql/`; deferred post-v0.1 |
| Provenance system vs. entity events table split | sec6 | Low | **Resolved by sec9.6** — single `ProvenanceRecord` table for both entity and system events; system operations (`migration_applied`, `reference_data_installed`) carry `entity_id = null`. One table, one code path |
| Auth / RBAC | sec8 | **✅ Resolved (Phase 3)** | `BridgeAuthMiddleware` spec in sec8; Bridge owns auth, Hippo trusts injected headers; actor flows into provenance |
| GA4GH DRS server (read-only) | sec4 | High | v0.4.0 target — `GET /ga4gh/drs/v1/objects/{entity_id}` resolves entity UUID → access_methods (s3/https/file). Thin read-only router over existing entity storage. No new data model; entity URI is the download target. Checksums from provenance if available. Enables external tools (Terra, Galaxy, other Canon instances) to resolve `drs://` URIs. Canon DRS client for consuming external DRS URIs deferred to Canon v0.3. |
| `HippoClient.schema_references(entity_type)` | — | **✅ Implemented (Hippo v0.4)** | Reads `FieldDefinition.references` from already-loaded schema. Returns `[{field, target_entity_type}]` for each field with `references: {entity_type: <name>}` declared in schema YAML. REST endpoint: `GET /schemas/{entity_type}/references`. Works today — caller schemas must declare `references:` on foreign-key fields. |

---

## How to Use This Spec

Each section document is self-contained and includes `Depends on` and `Feeds into` headers
to make inter-document dependencies explicit. When starting a new section, read the documents
it depends on first.

This spec is designed to feed into the openplan pipeline:
```
Spec sections → openplan vision.yaml → roadmap → epics → features → OpenSpec
```

Each completed section maps to one or more epics in the openplan roadmap.
