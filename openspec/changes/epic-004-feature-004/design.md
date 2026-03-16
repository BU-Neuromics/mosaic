## Context

Hippo is the Metadata Tracking Service (MTS) for the BASS platform. Currently, the system tracks entity state but lacks historical tracking and point-in-time query capabilities. Users need to query entity state at specific points in time and view the complete change history for audit and debugging purposes.

The implementation affects the Core SDK layer (`hippo/core/`) and requires changes to the data model and query engine.

## Goals / Non-Goals

**Goals:**
- Implement `history(entity_id)` operation returning all changes in chronological order with timestamps, user IDs, and operation types
- Implement `state_at(entity_id, timestamp)` operation returning entity state as it existed at a specific point in time
- Include operation ID and previous state hash in each history entry
- Support querying state at any point from entity creation to current time
- Return proper errors for invalid timestamps (before creation)

**Non-Goals:**
- Real-time change notifications (future work)
- Cross-entity lineage tracking (future work)
- Full audit log export functionality (future work)
- Migration of existing data to historical records (v1 only tracks from implementation forward)

## Decisions

### 1. Storage Approach: Provenance Log Append-Only
**Decision**: Store all entity state transitions in a provenance log table rather than maintaining versioned snapshots.

**Rationale**: More storage-efficient for entities with many modifications, enables complete audit trail, and naturally supports temporal queries. The design doc (sec3) already specifies temporal fields live in the provenance log.

**Alternative Considered**: Versioned snapshots - rejected due to storage overhead with frequent modifications.

### 2. Temporal Query Strategy: Timestamp-Based Filtering
**Decision**: Use timestamp-based filtering in the QueryEngine rather than a separate temporal API.

**Rationale**: Maintains consistency with existing query patterns, reduces API surface area, and leverages existing index infrastructure.

**Alternative Considered**: Separate temporal query methods - rejected to keep API surface minimal.

### 3. State Hash Algorithm: SHA-256 of Serialized State
**Decision**: Use SHA-256 hash of the entity's serialized state (excluding system fields) for the previous state hash.

**Rationale**: Provides collision resistance, deterministic, and fast to compute. SHA-256 is already available in Python's standard library.

**Alternative Considered**: UUID-based references - rejected as hashes provide integrity verification.

## Risks / Trade-offs

- **[Risk] Query Performance**: Historical queries across large datasets could be slow.
  - **Mitigation**: Implement database indexes on (entity_id, timestamp) for provenance log queries.

- **[Risk] Storage Growth**: Append-only provenance log will grow unbounded.
  - **Mitigation**: Consider archival strategies in future. For v1, rely on database pruning capabilities.

- **[Risk] Timezone Handling**: Timestamp ambiguity across timezones could cause confusion.
  - **Mitigation**: Store all timestamps in UTC, accept UTC in queries, document timezone behavior clearly in API.

## Migration Plan

1. **Deploy new schema**: Add provenance_log table with new indexes
2. **Enable tracking**: Modify IngestionPipeline to write to provenance_log on each entity modification
3. **Release SDK**: Update HippoClient with history() and state_at() methods
4. **No rollback needed**: No breaking changes to existing API - new operations only

## Open Questions

- Should history be available for all entity types or configurable per schema?
- Do we need pagination for entities with very large history (>1000 changes)?
