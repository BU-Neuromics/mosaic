# Hippo — Metadata Tracking Service
## Specification Index

**Codename:** Hippo  
**Component:** Metadata Tracking Service (MTS)  
**Version:** 0.1-draft  

---

## Document Map

| File | Section | Status | Notes |
|---|---|---|---|
| `sec1_overview.md` | 1. Overview & Scope | 🔄 In review | Generalized — domain-specific terms removed |
| `sec2_architecture.md` | 2. Architecture | 🔄 In review | Generic entity routing, domain-neutral examples |
| `sec3_data_model.md` | 3. Data Model | 🔄 In review | v0.3 — conceptual model only; storage detail moved to sec3b |
| `sec3b_relational_storage.md` | 3b. Relational Storage Mapping | 🔄 In review | Reference impl for SQLite/PostgreSQL adapters |
| `sec4_api_layer.md` | 4. API Layer | ⬜ Not started | |
| `sec5_ingestion.md` | 5. Ingestion & Integration | ⬜ Not started | |
| `sec6_provenance.md` | 6. Provenance & Audit | ⬜ Not started | Closely coupled to sec3 |
| `sec7_nfr.md` | 7. Non-Functional Requirements | ⬜ Not started | |
| `appendix_a_example_schema_omics.md` | Appendix A. Example Schema (Omics) | 🔄 In review | Example deployment config; not system spec |

---

## Key Decisions Log

| Decision | Choice | Section |
|---|---|---|
| Deployment model | SDK-first; REST and GraphQL are independent transport adapters | sec2 |
| Async strategy | Sync SDK for v0.1; revisit at PostgreSQL adapter | sec2 |
| REST deployment | Standalone (`hippo serve`) wrapping embedded `app` object | sec2 |
| Plugin system | Entry points (`hippo.storage_adapters`, `hippo.external_adapters`) | sec2 |
| Storage backend v0.1 | SQLite via stdlib `sqlite3` | sec2 |
| Data model approach | Config-driven relational + graph-shaped API; graph DB as future adapter | sec3 |
| Temporal metadata | Provenance log only — not stored on entities; computed at read time | sec3 |
| Entity lifecycle | `is_available` boolean; storage adapters optimize for this filter | sec3, sec3b |
| Lifecycle semantics | Reason for unavailability stored in provenance events, not on entities | sec3 |
| Supersession | System-level `superseded_by` relationship; atomic SDK operation | sec3 |
| Schema authoring | Hippo DSL (YAML/JSON) compiled transiently to LinkML | sec3 |
| LinkML output | On-demand via `hippo compile-schema`; not auto-committed | sec3 |
| Graph DB | Future adapter option; not v0.1 scope | sec3 |
| Multi-tenancy | Out of scope for v0.1 | sec3 |
| Conceptual/storage separation | Sec3 defines conceptual data model only; relational storage mapping in sec3b | sec3, sec3b |
| Domain-neutral spec | System spec contains no domain-specific schema; omics types removed | sec1, sec2, sec3 |

---

## Additional Key Decisions (from Platform Design Sessions)

See `platform/design/INDEX.md` for full rationale and design details.

| Decision | Choice |
|---|---|
| Schema inheritance semantics | `base:` creates polymorphic (is-a) inheritance — subtypes are queryable as their parent type |
| Validator `entity_types` matching | Subtype-aware — declaring a parent type covers all subtypes; declaring a child type targets only that subtype; redundant entries emit a startup warning |
| Config-driven validation | `validators.yaml` supports unified validator format with CEL conditions, `expand` path pre-fetching, `when` pre-conditions, `requires` shorthand, and `existing` context for updates |
| CEL expression language | Used for config-driven validator conditions (not a custom DSL) — sandboxed, proven, supports AND/OR/list macros |
| Expand path syntax | `field`, `field.child`, `field[]`, `field[].child` — explicit pre-fetch declarations; paths deduplicated; batch-fetched for list nodes; cycle detection via visited set; `max_expand_list_size` safety cap |
| Lazy evaluation rejected | Explicit `expand` paths preferred — CEL short-circuit makes implicit I/O non-deterministic; explicit paths are auditable |
| Built-in validator presets | `ref_check`, `count_constraint`, `immutable_field`, `field_required_if`, `no_self_ref` ship as ergonomic shortcuts expanding to unified format — not separate code paths |
| External adapter stubs | STARLIMS, HALO, Donor DB concrete implementations move to Cappella; `ExternalSourceAdapter` ABC stays in Hippo |
| Reference loader plugin system | `hippo.reference_loaders` entry point; `ReferenceLoader` ABC ships `schema_fragment()`; install auto-migrates; `requires:` block in schema.yaml; collision → `ConfigError` |
| Fuzzy search | `EntityStore.search()` ABC method; per-field `search:` mode in schema config; `ScoredMatch` core SDK type; adapter capability declaration at startup |

## Open Questions

| Question | Section | Priority |
|---|---|---|
| ~~WorkflowRun execution state — enum extension vs properties JSON?~~ | sec3/sec4 | ✅ Resolved — dedicated enum field (domain schema decision, no longer in system spec) |
| Where does the omics schema ultimately live? (config repo, `schemas/omics/`, deferred) | — | Medium |
| Pagination strategy for large query results | sec4 | High |
| Ingestion idempotency key design | sec5 | High |
| Provenance retention policy | sec6 | Medium |

---

## Pending Updates (from Platform Design Sessions)

The following changes are required based on decisions recorded in `platform/design/INDEX.md`. They should be applied before sec2–sec5 are marked complete.

| Section | Change needed | Source decision |
|---|---|---|
| `sec2_architecture.md` | Add unified config validator infrastructure to package structure: `validators.yaml` loader, expand path engine, CEL evaluator, built-in preset registry, `WriteValidator` ABC, `WriteOperation` + `ValidationResult` types | Unified validation architecture |
| `sec2_architecture.md` | Add `hippo.write_validators` entry point group to plugin system section | Unified validation architecture |
| `sec2_architecture.md` | Add `EntityStore.search()` + `ScoredMatch` type to adapter interface; add adapter capability declaration | Fuzzy search |
| `sec2_architecture.md` | Add `ReferenceLoader` ABC + `hippo.reference_loaders` entry point to plugin system | Reference loader plugin system |
| `sec2_architecture.md` | Remove concrete external adapter stubs (STARLIMS, HALO, Donor DB) from package structure — `ExternalSourceAdapter` ABC remains | Adapter boundary |
| `sec3_data_model.md` | Formalise `base:` as polymorphic (is-a) inheritance; document subtype semantics for queries, validators, and relationships | Schema inheritance |
| `sec3_data_model.md` | Add `search` field declaration to schema config field type system | Fuzzy search |
| `sec3_data_model.md` | Add `requires:` block to schema config format | Reference loader plugin system |
| `sec3b_relational_storage.md` | Add storage strategy for polymorphic inheritance (type discriminator column vs. joined tables) | Schema inheritance |
| `sec4_api_layer.md` | *(not started)* Include fuzzy search endpoint + `ScoredMatch` response | Fuzzy search |
| `sec5_ingestion.md` | *(not started)* Include `hippo reference` CLI commands + `ReferenceLoader` lifecycle | Reference loader plugin system |

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
