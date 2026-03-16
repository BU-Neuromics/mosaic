## Context

The Hippo Metadata Tracking Service currently lacks native support for managing relationships between entities. The system stores entities and their attributes but does not provide a way to define, query, or traverse connections between entities. Users need to establish and query relationships like "sample belongs to donor", "order contains results", or "container holds specimens".

The proposal requests implementing three core operations: `relate` (create connections), `unrelate` (remove connections), and `traverse` (query connected entities with depth/filter support). This requires changes to the data model, SDK, and potentially the transport layer.

## Goals / Non-Goals

**Goals:**
- Implement `relate` operation to create typed relationships between entities with metadata
- Implement `unrelate` operation to remove specific relationships with history tracking
- Implement `traverse` operation to query entity graphs with depth limits and filters
- Store relationship metadata (timestamp, creator) for audit purposes
- Support multiple relationship types between the same entity pair
- Add authentication/authorization checks for relationship operations

**Non-Goals:**
- Graph visualization or UI components
- Batch relationship operations (bulk relate/unrelate)
- Relationship validation or constraint enforcement at write time
- Circular relationship detection
- Bidirectional relationship inference

## Decisions

1. **Relationship storage approach: Separate relationship table**
   - Alternative: Embed relationships in entity JSONB column
   - Chosen: Separate table allows efficient traversal queries and index optimization
   - Rationale: Traversal queries require scanning all relationships; JSONB would require loading all entities

2. **Relationship metadata model**
   - Store: source_id, target_id, relationship_type, created_at, created_by, metadata (JSONB)
   - Rationale: Supports audit requirements and flexible metadata per relationship

3. **Traversal algorithm: Recursive CTE**
   - Alternative: Build in-memory graph on each query
   - Chosen: Database-level recursion with depth limiting
   - Rationale: Efficient for large graphs, reduces memory usage

4. **Relationship type validation: Allow any string**
   - Alternative: Pre-defined relationship types in schema
   - Chosen: Open model allowing any relationship type
   - Rationale: Flexibility for domain extensions without schema changes

## Risks / Trade-offs

- **Graph traversal performance**: Deep traversals on large graphs could be slow. → Implement depth limits and consider query timeouts
- **No transaction support for multi-step operations**: Relate and unrelate are single operations. → Document as limitation, users can wrap in external transactions
- **No relationship constraints**: System cannot enforce "donor must exist before relationship". → Validation moved to application layer if needed
- **Authentication gap**: Proposal requires auth check but current SDK has no auth. → Implement authz framework or document limitation

## Migration Plan

1. Add relationship table to database schema (backward compatible)
2. Implement SDK relationship methods (relate, unrelate, traverse)
3. Add tests for all operations
4. Deploy SDK version
5. Document new capabilities

No migration needed for existing data; relationships are entirely new functionality.

## Open Questions

- Should relationship types be validated against the schema?
- How to handle circular relationships in traversal (return error or deduplicate)?
- Should traverse return full entities or just entity references?
