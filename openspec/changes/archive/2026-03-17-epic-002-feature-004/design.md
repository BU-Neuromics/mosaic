## Context

The Hippo Metadata Tracking Service needs to track changes to entities (CREATE, SOFT_DELETE operations) in a dedicated provenance table. Currently, entity changes are not persisted with full audit history. This design addresses implementing provenance tracking at the database level with immutable records.

## Goals / Non-Goals

**Goals:**
- Implement a provenance table in SQLite that stores immutable records of entity operations
- Track CREATE and SOFT_DELETE operations with entity ID, operation type, timestamp, and user context
- Ensure all provenance records are created within the same transaction as the entity operation
- Maintain data immutability by storing original entity data on soft-delete

**Non-Goals:**
- Support for UPDATE operations (future scope)
- Cross-database migration (SQLite only for this implementation)
- External system integration for provenance sync

## Decisions

1. **Provenance table schema**: Store entity_id, operation_type, timestamp, user_context, and payload as JSON
   - Rationale: Flexible schema allows storing varying entity structures without schema migrations

2. **Transaction-bound provenance events**: Create provenance records in the same transaction as entity operations
   - Rationale: Ensures atomicity - either both entity and provenance records are created, or neither

3. **JSON payload for entity data**: Store complete entity state in JSON column
   - Rationale: Simplifies querying and ensures original data is preserved exactly as-is

4. **No hard deletes in provenance**: All operations are immutable records
   - Rationale: Full audit trail required; no deletion of historical records

## Risks / Trade-offs

- [Risk] JSON payload may impact query performance → Mitigation: Add indexed columns for common queries (entity_id, operation_type, timestamp)
- [Risk] Large entity payloads bloat database → Mitigation: Implement pagination/archive strategy for old records (future)
- [Risk] User context may be unavailable in some scenarios → Mitigation: Use system default or null with logging
