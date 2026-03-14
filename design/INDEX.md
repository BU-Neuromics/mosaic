# Hippo — Metadata Tracking Service
## Specification Index

**Codename:** Hippo  
**Component:** Metadata Tracking Service (MTS)  
**Version:** 0.1 — First Complete Draft  
**Status:** Ready for review

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

---

## Open Questions

Items requiring a future design decision before implementation. Deferred items are explicitly
out of scope for v0.1 and documented here for tracking.

| Question | Section | Priority | Status |
|---|---|---|---|
| Where does the example omics schema ultimately live? | — | Low | Open — config repo, `schemas/omics/`, or community `hippo-reference-omics` package |
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
