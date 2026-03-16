## Context

The proposal outlines implementing a full-text search query API for the Hippo SQLite adapter. This builds on epic-008-feature-001 which established FTS5 virtual table infrastructure. The search capability enables clients to retrieve entities by relevance-ranked full-text matches on fields marked with `search: fts` in the schema.

This change depends on:
- `epic-008-feature-001`: FTS5 virtual table creation and maintenance
- `epic-004-feature-001`: EntityStore CRUD operations (put, get, query)

## Goals / Non-Goals

**Goals:**
- Implement `EntityStore.search()` method returning `list[ScoredMatch]`
- Order results by FTS5 BM25 relevance score descending
- Support `min_score` parameter to filter low-relevance results
- Support `limit` parameter to cap result count
- Return scores in range [0.0, 1.0] normalized from BM25
- Raise `SearchCapabilityError` when searching non-FTS fields

**Non-Goals:**
- Implementing search result pagination (future)
- Supporting complex FTS5 query syntax directly (boolean operators, phrases)
- Search result highlighting/snippets (future)
- Ranking algorithm customization beyond BM25

## Decisions

### 1. Score Normalization Approach
**Decision:** Normalize BM25 scores to [0.0, 1.0] range using exponential decay.
- **Rationale:** Raw BM25 scores are unbounded and depend on document frequency. Normalization provides consistent client-facing API.
- **Formula:** `normalized_score = 1.0 / (1.0 + exp(-k * (bm25 - threshold)))` where k controls curve steepness

### 2. Search API Signature
**Decision:** Add `search(query, entity_type, field_name, min_score=0.0, limit=100)` to EntityStore.
- **Rationale:** Explicit entity_type and field_name parameters prevent ambiguity. Defaults follow common patterns.
- **Alternative considered:** Infer from query context - rejected due to complexity

### 3. Error Handling Strategy
**Decision:** Raise `SearchCapabilityError` for non-FTS fields at search time.
- **Rationale:** Schema may evolve; checking at query time ensures runtime accuracy.
- **Error includes:** field name, entity type, suggestion to add `search: fts`

### 4. Result Type Design
**Decision:** Return `ScoredMatch(entity_id, score, highlights=None)` named tuple.
- **Rationale:** Simple, immutable, clear semantics. Future-proof for adding highlights.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| BM25 score distribution varies by corpus | Normalize per-query using max score in results as denominator |
| Empty results for common terms | Return empty list (valid outcome, not error) |
| Non-FTS field search fails silently | Raise SearchCapabilityError with helpful message |
| Large result sets cause memory pressure | Enforce limit parameter default (100), support higher if needed |

## Migration Plan

This is a new API method - no migration required. Existing code continues to work.

**Rollback:** Remove search method from EntityStore; clients receive AttributeError.

## Open Questions

1. **Highlighting:** Should we return matched text snippets? (Deferred to future - requires FTS5 highlight() API)
2. **Query syntax:** Support advanced FTS5 operators (AND, OR, NOT, phrases)? (Deferred - start with simple term matching)
3. **Multi-field search:** Search across multiple FTS fields in one query? (Deferred - single field first)
