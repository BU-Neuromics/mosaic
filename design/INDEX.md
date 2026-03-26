# Hippo — Metadata Tracking Service
## Specification Index

**Codename:** Hippo  
**Component:** Metadata Tracking Service (MTS)  
**Version:** 0.1 — Implementation Ready  
**Status:** Ready for implementation

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
| `appendix_a_example_schema_omics.md` | Appendix A. Example Schema (Omics) | ✅ Draft v0.1 | Complete DSL with `search:`, polymorphic extension example |
| `appendix_b_implementation_guide.md` | Appendix B. Implementation Guide | ✅ Draft v0.1 | Build order, module map, error hierarchy, invariants, test strategy, OpenSpec mapping |
| `reference_hippo_yaml.md` | Reference: `hippo.yaml` Config Schema | ✅ Draft v0.1 | All valid keys, types, defaults, env var substitution, minimal configs |
| `reference_validators_yaml.md` | Reference: `validators.yaml` Format | ✅ Draft v0.1 | Complete field spec, expand syntax, all built-in presets, execution semantics |
| `reference_cel_context.md` | Reference: CEL Evaluation Context | ✅ Draft v0.1 | All context variables, CEL types, expanded field shapes, available functions, common patterns |

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
| Schema authoring | Hippo DSL (YAML/JSON) compiled transiently to LinkML | sec3 |
| LinkML output | On-demand via `hippo compile-schema`; not auto-committed | sec3 |
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
| Root namespace canonicalization | `root.Donor` normalized to `"Donor"` at registry ingestion; only unqualified form in `SchemaConfig` and storage | sec3 |
| Namespace backwards compatibility | Schemas without `namespace:` key load unchanged; no data migration required for existing deployments | sec3 |

---

## Open Questions

Items requiring a future design decision before implementation. Deferred items are explicitly
out of scope for v0.1 and documented here for tracking.

| Question | Section | Priority | Status |
|---|---|---|---|
| Where does the example omics schema ultimately live? | — | Low | Open — config repo, `schemas/omics/`, or community `hippo-reference-omics` package |
| Entity type remapping / namespace migration path (OQ1) | sec3 §3.12 | High | Open — no migration path exists for moving `Sample` (root) to `tissue.Sample`; must be resolved before any production namespace adoption of existing entities. Options: `hippo migrate --remap`, namespace aliasing, or out-of-band migration script |
| Canonical form for root-namespace entities in storage (OQ2) | sec3 §3.11 | Low | Decided — store as `"Donor"` (unqualified); registry normalizes `root.*` to unqualified at load time; documented as a firm invariant |
| Ingestion idempotency for live webhook integrations | sec5 | High | Deferred — ExternalID upsert is the stable foundation; webhook retry deduplication needs a dedicated design session when live integrations are scoped |
| Bulk availability change endpoint | sec4 | Medium | Deferred — `POST /entities/{type}/bulk-availability` for dataset archival |
| OR filter composition in query API | sec4 | Low | Deferred — AND-only v0.1; CEL expression filter endpoint is future |
| Per-validator timeout | sec2 | Low | Deferred — plugin validators should complete in <100ms; configurable timeout post-v0.1 |
| `hippo_poll` efficiency at scale | sec3b/sec6 | Medium | Deferred — provenance timestamp index handles current workload; denormalised `updated_at` column if needed at scale |
| Schema version check on writes (503 on mismatch) | sec7 | Medium | Planned for v0.2 — roadmap documented in sec7 §7.3 |
| Dynamic schema reload via polling | sec7 | Medium | Planned for v0.3 — roadmap documented in sec7 §7.3 |
| Expand-contract convention enforcement in `hippo migrate` | sec2/sec3 | Medium | Planned for v0.3+ — roadmap documented in sec7 §7.3 |
| Cursor-based pagination | sec4 | Low | Deferred post-v0.1 |
| GraphQL transport | sec2 | Low | Reserved in `hippo/graphql/`; deferred post-v0.1 |
| Provenance system vs. entity events table split | sec6 | Low | Open — `MigrationApplied` and `ReferenceDataInstalled` stored with `entity_id = null`; separate `system_events` table is an alternative |
| Auth / RBAC | sec7 | High (post-v0.1) | Auth middleware stub in place; JWT/API key/RBAC design deferred |
| GA4GH DRS server (read-only) | sec4 | High | v0.4.0 target — `GET /ga4gh/drs/v1/objects/{entity_id}` resolves entity UUID → access_methods (s3/https/file). Thin read-only router over existing entity storage. No new data model; entity URI is the download target. Checksums from provenance if available. Enables external tools (Terra, Galaxy, other Canon instances) to resolve `drs://` URIs. Canon DRS client for consuming external DRS URIs deferred to Canon v0.3. |
| `HippoClient.schema_references(entity_type)` | — | **Priority — required for Cappella v0.1** | Returns the reference edge graph for an entity type: `{entity_type: str, references: [{field: str, target_entity_type: str, via_field: str}]}`. Reads already-loaded schema (SchemaConfig objects); approximately 20 lines of implementation. Cappella's collection resolver depends on this to infer entity traversal paths from dot-notation criteria (`donor.diagnosis`, `sample.tissue`) without hardcoded config. Add to HippoClient SDK and expose via REST: `GET /schema/{entity_type}/references`. |

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
