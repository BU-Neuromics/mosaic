## Context

This change implements database-level immutable triggers for provenance records in Hippo's SQLite storage adapter. Provenance records track the history and lineage of data - they must remain unchanged once committed to ensure data integrity and auditability. Currently, the application relies on application-level checks to prevent modifications, but this design adds a second layer of protection at the database level.

### Current State
- Hippo uses SQLite for storage with provenance records stored in a dedicated table
- Application-level logic prevents updates to provenance records, but this can be bypassed
- No database-level enforcement exists for immutability

### Constraints
- SQLite has specific trigger syntax and limitations
- Must work within SQLite's transaction model
- Triggers must not impact performance of read operations

## Goals / Non-Goals

**Goals:**
- Implement SQLite triggers that prevent UPDATE operations on provenance records
- Implement SQLite triggers that prevent DELETE operations on provenance records
- Ensure triggers activate on COMMIT to maintain transaction scope immutability
- Protect all protected fields: primary key, timestamp, metadata, content

**Non-Goals:**
- Implementing this for other database backends (PostgreSQL future work)
- Adding application-level immutability logic (already exists)
- Migration scripts for existing data

## Decisions

1. **Trigger Type**: Use BEFORE triggers on UPDATE and DELETE operations
   - Rationale: SQLite supports BEFORE triggers that fire before the operation executes, allowing us to raise an exception to block the operation
   - Alternative considered: AFTER triggers (can't prevent the operation)

2. **Scope**: Triggers fire at COMMIT time via "PRAGMA recursive_triggers" 
   - Rationale: SQLite triggers fire immediately, but we need transaction-scoped immutability
   - Implementation: Use RAISE(ROLLBACK) within triggers to abort the entire transaction

3. **Fields Protected**: Primary key, timestamp, metadata, content
   - Rationale: These fields define the core provenance record identity and must not change

## Risks / Trade-offs

- **Risk**: Trigger overhead on write operations
  - Mitigation: Minimal performance impact; triggers only fire on provenance table operations
  
- **Risk**: SQLite version compatibility
  - Mitigation: Use standard SQL trigger syntax supported by SQLite 3.6+

- **Risk**: Testing difficulty
  - Mitigation: Include integration tests that verify trigger behavior

## Migration Plan

1. Add trigger creation SQL to storage adapter initialization
2. Triggers are created idempotently (DROP IF EXISTS before CREATE)
3. No migration needed for existing data - triggers apply to future operations

## Open Questions

- Should triggers also prevent INSERT of records with past timestamps?
- Should there be an admin override mechanism for data修复?
