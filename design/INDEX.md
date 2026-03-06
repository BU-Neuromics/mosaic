# Hippo — Omics Metadata Tracking Service
## Specification Index

**Codename:** Hippo  
**Component:** Metadata Tracking Service (MTS)  
**Version:** 0.1-draft  

---

## Document Map

| File | Section | Status | Notes |
|---|---|---|---|
| `sec1_overview.md` | 1. Overview & Scope | ✅ Complete | Reviewed and approved |
| `sec2_architecture.md` | 2. Architecture | ✅ Complete | Reviewed and approved |
| `sec3_data_model.md` | 3. Data Model | 🔄 In review | v0.2 — system fields, status enum, LinkML DSL updated |
| `sec4_api_layer.md` | 4. API Layer | ⬜ Not started | |
| `sec5_ingestion.md` | 5. Ingestion & Integration | ⬜ Not started | |
| `sec6_provenance.md` | 6. Provenance & Audit | ⬜ Not started | Closely coupled to sec3 |
| `sec7_nfr.md` | 7. Non-Functional Requirements | ⬜ Not started | |

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
| Temporal metadata | Provenance log only — not stored on entity tables | sec3 |
| Entity lifecycle | `status` enum column; partial index on `active` | sec3 |
| Status values | active, archived, superseded, deleted, distributed, removed | sec3 |
| Supersession | System-level `superseded_by` relationship; atomic SDK operation | sec3 |
| Schema authoring | Hippo DSL (YAML/JSON) compiled transiently to LinkML | sec3 |
| LinkML output | On-demand via `hippo compile-schema`; not auto-committed | sec3 |
| Workflow tracking | WorkflowRun in default schema; execution state in `properties` | sec3 |
| Graph DB | Future adapter option; not v0.1 scope | sec3 |
| Multi-tenancy | Out of scope for v0.1 | sec3 |

---

## Open Questions

| Question | Section | Priority |
|---|---|---|
| WorkflowRun execution state — enum extension vs properties JSON? | sec3/sec4 | Medium |
| Pagination strategy for large query results | sec4 | High |
| Ingestion idempotency key design | sec5 | High |
| Provenance retention policy | sec6 | Medium |

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
