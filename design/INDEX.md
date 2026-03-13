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

| Section | Change needed |
|---|---|
| `sec2_architecture.md` | Add `WriteValidator` ABC + `hippo.write_validators` entry point; add `WriteOperation` + `ValidationResult` types to package structure |
| `sec2_architecture.md` | Add `EntityStore.search()` + `ScoredMatch` type; add adapter capability declaration |
| `sec2_architecture.md` | Add `ReferenceLoader` ABC + `hippo.reference_loaders` entry point to plugin system |
| `sec2_architecture.md` | Remove concrete external adapter stubs (STARLIMS, HALO, Donor DB) from package structure — `ExternalSourceAdapter` ABC remains |
| `sec3_data_model.md` | Add `search` field declaration to schema config field type system |
| `sec3_data_model.md` | Add `requires:` block to schema config format |
| `sec4_api_layer.md` | *(not started)* Include fuzzy search endpoint + `ScoredMatch` response |
| `sec5_ingestion.md` | *(not started)* Include `hippo reference` CLI commands + `ReferenceLoader` lifecycle |

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
