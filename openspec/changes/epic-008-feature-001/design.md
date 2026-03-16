# FTS5 Virtual Table Management - Technical Design

## Context

The proposal outlines adding SQLite FTS5 (Full-Text Search) virtual table support to Hippo. This enables full-text search capabilities on entity fields marked with `search: fts` in the schema. The implementation requires:

- Automatic FTS5 table creation during schema migration
- Real-time index updates on entity writes
- Proper handling of entity lifecycle (create, update, delete, availability changes)

This change depends on:
- `epic-002-feature-002`: Schema configuration system
- `epic-002-feature-003`: Storage adapter interface

## Goals / Non-Goals

**Goals:**
- Create FTS5 virtual tables for schema fields declared with `search: fts`
- Keep FTS tables synchronized with main entity storage in the same transaction
- Handle all entity lifecycle events (create, update, delete, availability transitions)
- Support backfilling existing data when new FTS fields are added
- Enable full-text search queries against indexed fields

**Non-Goals:**
- Implementing search query API (future capability)
- Supporting non-SQLite backends with FTS (PostgreSQL FTS is different)
- Real-time search result ranking algorithms
- Multi-language tokenizer support beyond default

## Decisions

### 1. FTS Table Storage Approach
**Decision:** Create separate FTS5 virtual tables per entity type and field.
- **Rationale:** Simplifies migration and rollback. Each FTS table maps 1:1 to a source entity table's FTS-indexed field.
- **Alternative considered:** Single unified FTS table with type prefixes - adds complexity for queries and migrations.

### 2. Transaction Strategy
**Decision:** FTS updates occur in the same transaction as the main entity write.
- **Rationale:** Ensures atomicity - either both the entity and its FTS entry succeed or both fail.
- **Implementation:** Use SQLite's transaction support; FTS INSERT/UPDATE/DELETE in same connection.

### 3. Content Storage Mode
**Decision:** Use FTS5 `content=` external content mode.
- **Rationale:** Allows FTS table to reference the main entity table rather than duplicating content. Reduces storage and ensures consistency.
- **Migration consideration:** Requires careful handling during schema changes.

### 4. Migration Backfill Strategy
**Decision:** Backfill FTS tables during `hippo migrate` using batched inserts.
- **Rationale:** Large datasets may require significant time; batching prevents memory issues.
- **Alternative considered:** Lazy backfill on first search - rejected due to incomplete search results until all data indexed.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Large entity tables cause slow backfills | Use batched inserts (1000 rows per batch), add progress logging |
| Schema changes to FTS fields mid-flight | Use schema versioning, require migration lock during changes |
| FTS table out of sync with main table | Always use transactions; add integrity check CLI command |
| FTS queries return stale data | FTS5 with external content reflects source table immediately |

## Migration Plan

1. **Schema Provisioning Phase:**
   - Detect fields with `search: fts` in schema
   - Generate FTS5 CREATE TABLE statements
   - Execute in migration transaction

2. **Backfill Phase:**
   - Query all entities with FTS-indexed fields
   - Insert into FTS tables in batches
   - Log progress and handle errors

3. **Runtime Phase:**
   - Intercept entity write operations
   - Update FTS tables in same transaction
   - Handle availability=false as DELETE to FTS

**Rollback:** Drop FTS5 tables via `DROP TABLE IF EXISTS` (virtual tables drop cleanly).

## Open Questions

1. **Query API:** Should we expose FTS query syntax directly or provide a simplified search API? (Deferred to future change)
2. **Tokenizer:** Should we support custom tokenizers for domain-specific text processing? (Deferred - default Unicode61 for v1)
3. **Indexing Performance:** For high-volume writes, consider async FTS indexing (future optimization)
