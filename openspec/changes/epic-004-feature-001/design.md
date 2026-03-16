## Context

This change implements core CRUD operations for the HippoClient SDK. The HippoClient is the public API for the Hippo Metadata Tracking Service. This includes entity creation/update (put), retrieval (get), and search (query) capabilities.

Current state: The HippoClient class exists as a shell but lacks the core operations needed to interact with entities.

## Goals / Non-Goals

**Goals:**
- Implement `put(entity)` - Create or update entities with versioning
- Implement `get(entity_id)` - Retrieve entities by ID with metadata
- Implement `query(filters)` - Query entities with filter criteria
- Implement state management for entity availability

**Non-Goals:**
- Advanced query features (aggregation, complex joins)
- Batch operations
- Transaction support
- External system adapters (STARLIMS, HALO, Donor DB)

## Decisions

1. **Storage Backend**: Use SQLite for initial implementation
   - Rationale: Simple, file-based, no external dependencies for v0.1
   - Alternative: PostgreSQL (deferred to future)

2. **Versioning Strategy**: Increment version number on each update
   - Rationale: Simple approach suitable for initial release
   - Alternative: Timestamp-based versioning (overkill for v0.1)

3. **Query Implementation**: In-memory filtering with SQLite WHERE clauses
   - Rationale: Leverages SQLite capabilities without complex ORM
   - Alternative: Full-text search (deferred)

4. **Entity Validation**: Schema-driven validation via LinkML
   - Rationale: Follows config-driven relational model from architecture
   - Alternative: Manual validation (not scalable)

## Risks / Trade-offs

- [Performance] Single-file SQLite may not scale → Mitigation: Design for PostgreSQL migration path
- [Validation] LinkML validation overhead → Mitigation: Cache compiled schemas
- [Versioning] No conflict resolution → Mitigation: Last-write-wins for v0.1, future optimistic locking

## Migration Plan

1. Deploy new SDK with CRUD operations
2. No database migration needed (new tables)
3. Rollback: Previous SDK version still works (no breaking changes)

## Open Questions

- Should query support pagination? (Deferred to future)
- How to handle soft deletes vs. hard deletes? (Using is_available flag per spec)
