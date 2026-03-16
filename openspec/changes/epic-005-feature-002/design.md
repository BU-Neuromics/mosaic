# Technical Design: Expand Path Parser and Batch Fetcher

## Context

The Hippo SDK needs efficient data fetching capabilities through an expand mechanism that allows clients to request related entities in a single query. Currently, the system lacks a robust parser for expand paths, a batch fetcher to optimize database queries, cycle detection to prevent infinite loops, and size validation.

**Current State:**
- No expand path parser exists
- Individual queries are made for each nested entity (N+1 problem)
- No cycle detection for circular references in expand paths
- No max size enforcement for expand path strings

**Constraints:**
- Must integrate with existing HippoClient API
- Must work with SQLite (v0.1) storage backend
- Must follow SDK-first principle (business logic in core, not transport)

## Goals / Non-Goals

**Goals:**
- Implement a robust expand path parser that correctly identifies all referenced fields and their parent-child relationships
- Implement a batch fetcher that performs one database query per entity list instead of N individual queries
- Implement cycle detection to detect circular references like "user.orders.items.user"
- Implement max size validation to prevent excessively long expand paths (default: 100 characters)
- Provide clear, descriptive error messages for all failure cases

**Non-Goals:**
- GraphQL support (future work)
- PostgreSQL optimization (future work)
- Caching layer (future work)
- Real-time subscription support

## Decisions

### 1. Parser Design: Recursive Descent Parser

**Decision:** Use a recursive descent parser for expand path parsing rather than regex-based approach.

**Rationale:**
- Better error reporting with precise location of syntax errors
- Easier to extend with additional validation rules
- Clearer separation between lexical analysis and semantic validation

**Alternative Considered:** Regex-based parsing - Rejected because it makes error messages vague and is harder to validate complex nested structures.

### 2. Batch Fetcher: Entity-Level Batching

**Decision:** Group by entity type and execute one query per entity list.

**Rationale:**
- Simpler to implement and debug
- Works well with existing SQLAlchemy models
- Avoids complex join strategies that may vary between backends

**Alternative Considered:** Single query with joins - Rejected because different storage backends handle joins differently, and the current SQLite backend may have performance issues with deep joins.

### 3. Cycle Detection: Graph Traversal

**Decision:** Build an adjacency graph from parsed path and detect cycles using DFS.

**Rationale:**
- Standard algorithm with well-understood behavior
- Can provide cycle path in error message for debugging
- O(V+E) time complexity is acceptable

**Alternative Considered:** Union-Find - Rejected because it doesn't easily provide cycle path information.

### 4. Error Handling: Custom Exception Hierarchy

**Decision:** Create a custom exception hierarchy with specific error types.

**Rationale:**
- Allows callers to handle different error cases specifically
- Consistent error format across the module
- Enables future i18n of error messages

**Alternative Considered:** Generic ValueError - Rejected because it doesn't allow callers to distinguish between different error conditions.

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|------|--------|------------|
| Deep nesting performance | High | Add configurable max depth limit (default: 5) |
| Memory usage with large result sets | Medium | Implement streaming/pagination for batch results |
| Parser complexity | Medium | Start with limited grammar, extend incrementally |
| Error message clarity | Low | Include path context in all error messages |

## Migration Plan

1. **Phase 1:** Implement expand path parser with validation (week 1)
2. **Phase 2:** Implement cycle detector integrated with parser (week 1)
3. **Phase 3:** Implement batch fetcher with entity-level grouping (week 2)
4. **Phase 4:** Integrate with HippoClient API, add tests (week 2)
5. **Phase 5:** Performance testing and optimization (week 3)

**Rollback Strategy:** Feature flag to disable expand functionality; legacy behavior preserved for clients not using expand.

## Open Questions

1. Should max_size be configurable per-schema or global?
2. Should batch fetcher support eager loading vs lazy loading options?
3. How to handle expand paths that reference non-existent fields?
