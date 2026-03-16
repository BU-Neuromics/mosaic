## Context

The Hippo metadata tracking service currently stores entities in SQLite without optimized indexing strategies. Query performance degrades as data volume grows, particularly for:
- Filtered queries on availability-scoped fields
- Aggregation queries that scan entire tables
- Frequently accessed columns without index support

The current implementation uses basic table structures from the relational storage mapping but lacks:
- Partial indexes scoped to `is_available = true`
- Summary views for common aggregation patterns
- Optimized query patterns for the SQLite backend

This design addresses performance optimization for SQLite storage in the Hippo Core SDK.

## Goals / Non-Goals

**Goals:**
- Implement partial indexes on frequently queried filtered columns
- Create summary views for common aggregation patterns (count, sum, avg)
- Ensure query planner correctly selects partial indexes
- Achieve measurable performance improvements (30%+ for indexed queries)

**Non-Goals:**
- PostgreSQL-specific optimizations (future work)
- Query caching layer (out of scope)
- Full-text search indexing (separate capability)
- Migration tooling for index management (covered by existing `hippo migrate`)

## Decisions

### Decision 1: Partial Index Strategy

**Choice:** Implement partial indexes scoped to `is_available = true` for all `indexed: true` fields.

**Rationale:**
- Hippo uses soft deletes via `is_available` boolean
- Most queries filter by `is_available = true`
- Partial indexes are smaller and faster than full indexes
- SQLite supports partial indexes natively

**Alternative Considered:**
- Full indexes on all indexed fields: Rejected - larger storage, slower writes, no benefit for common `is_available` filter

### Decision 2: Summary View Implementation

**Choice:** Create materialized summary views with refresh-on-read pattern.

**Rationale:**
- SQLite doesn't support native materialized views
- Pre-computed aggregates eliminate redundant calculations
- Refresh-on-read ensures consistency without background jobs
- Simple to implement and maintain

**Alternative Considered:**
- Trigger-based refresh: More complex, potential performance impact on writes
- Background refresh job: Adds infrastructure complexity, eventual consistency

### Decision 3: View Naming Convention

**Choice:** Use `summary_{entity_type}_{aggregation}` naming pattern.

**Rationale:**
- Clear purpose from name
- Avoids conflicts with entity tables
- Follows SQLite conventions

### Decision 4: Index Creation Timing

**Choice:** Indexes created during `hippo migrate` when field `indexed: true` is detected.

**Rationale:**
- Leverages existing migration infrastructure
- Automatic index management
- Schema-driven approach aligns with Hippo's config-first philosophy

## Risks / Trade-offs

### Risk 1: Index Selection by Query Planner
**Description:** SQLite query planner may not always choose partial indexes.
**Mitigation:** Use `EXPLAIN QUERY PLAN` to verify index usage; provide query hints if needed.

### Risk 2: Write Performance Impact
**Description:** Additional indexes increase write latency.
**Mitigation:** Partial indexes are smaller; benchmark with realistic write loads; allow field-level index configuration.

### Risk 3: View Consistency
**Description:** Summary views may become stale between reads.
**Mitigation:** Implement automatic refresh on read; consider timestamp tracking for cache invalidation.

### Risk 4: Schema Migration Complexity
**Description:** Adding indexes to existing tables requires migration.
**Mitigation:** Use existing `hippo migrate` infrastructure; support index creation in migration DDL.

## Migration Plan

1. **Phase 1:** Add partial index creation to migration DDL generation
2. **Phase 2:** Run migration on existing databases to create indexes
3. **Phase 3:** Implement summary view definitions
4. **Phase 4:** Update query patterns to use views
5. **Phase 5:** Benchmark and verify performance gains

**Rollback:** Migration can drop indexes via `DROP INDEX`; views can be dropped via `DROP VIEW`. No data loss.

## Open Questions

1. Should summary views be entity-type specific or cross-entity aggregations?
2. What refresh strategy for summary views in high-write scenarios?
3. How to expose index usage metrics for debugging?
