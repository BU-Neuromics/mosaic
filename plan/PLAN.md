# Hippo — Implementation Plan

**Status:** Ready for implementation  
**Planning tool:** OpenPlan → OpenSpec → OpenCode  
**Last updated:** 2026-03-14

---

## Summary

| Artifact | Count | Status |
|---|---|---|
| Vision | 1 | ✅ Defined |
| Roadmap | 1 | ✅ Validated |
| Epics | 8 | ✅ Decomposed |
| Features | 39 | ✅ All spec_ready |
| OpenSpec changes | 39 | ✅ Exported |

---

## Epic Overview

| Epic | Title | Features | Depends on |
|---|---|---|---|
| epic-001 | Foundation — Config, Schema Parsing, Core Types | 4 | — |
| epic-002 | SQLite Storage Adapter | 6 | epic-001 |
| epic-003 | Schema Validation — Tier 1 | 5 | epic-001, epic-002 |
| epic-004 | Full HippoClient SDK | 6 | epic-002, epic-003 |
| epic-005 | CEL Validators — Tier 2 and Plugin System | 5 | epic-003, epic-004 |
| epic-006 | REST Transport Layer | 4 | epic-004, epic-005 |
| epic-007 | CLI | 6 | epic-004, epic-005 |
| epic-008 | Full-Text Search (FTS5) | 3 | epic-002, epic-004 |

---

## Implementation Order

Epics must be implemented in dependency order. Parallelism opportunities noted:

```
epic-001 (Foundation)
    └── epic-002 (Storage)
            ├── epic-003 (Validation Tier 1)
            │       └── epic-004 (HippoClient SDK)
            │               ├── epic-005 (CEL Validators)
            │               │       ├── epic-006 (REST)
            │               │       └── epic-007 (CLI)
            │               └── epic-008 (FTS5)  ← can run parallel to epic-005
            └── epic-008 (FTS5)  ← storage dependency only
```

epic-008 (FTS5) can begin as soon as epic-002 and epic-004 are complete,
in parallel with epic-005/006/007.

---

## How to Use with OpenCode

Each feature has an OpenSpec change in `openspec/changes/<feature-id>/`.

To implement a feature with OpenCode:

```bash
# From hippo/plan/ directory — implement one feature at a time in epic order
cd /path/to/drylims-docs/hippo

# OpenCode reads the spec and the design docs (design/ is co-located)
# Point OpenCode at the openspec change for the feature you're implementing
```

**Key context files for coding agents:**

- `design/INDEX.md` — start here; links to all spec sections
- `design/appendix_b_implementation_guide.md` — build order, module map, invariants
- `design/reference_hippo_yaml.md` — complete config schema
- `design/reference_validators_yaml.md` — validators.yaml format
- `design/reference_cel_context.md` — CEL context variable specification
- `design/sec3b_relational_storage.md` — SQL DDL patterns
- `design/sec6_provenance.md` — provenance event model and storage

---

## Open Questions for Review

> These were flagged during planning and should be reviewed before or during implementation.

1. **epic-002 feature granularity** — WAL mode configuration (epic-002-feature-003) is
   very small. Consider merging into epic-002-feature-002 (schema generation) at
   implementation time if the coding agent finds the boundary too fine.

2. **epic-003-feature-005** (Schema Validation Integration Tests) — this is a test-only
   feature. Opinionated decision: kept separate so it doesn't bloat the implementation
   features, and so the coding agent has an explicit test-writing task. Review whether
   this is the right granularity.

3. **epic-004 / epic-005 boundary** — HippoClient (epic-004) is implemented without CEL
   validators. This means there's a window where the SDK works but business rules don't
   apply. The coding agent should not run integration tests that assume business rules
   until epic-005 is done. Consider adding a note to epic-004 OpenSpec specs.

4. **epic-006-feature-004** (OpenAPI Documentation Generation) — FastAPI auto-generates
   this; it may not need a standalone feature. Review at epic-006 implementation time.

---
