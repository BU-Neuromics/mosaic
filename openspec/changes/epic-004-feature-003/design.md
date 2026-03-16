## Context

The Hippo Metadata Tracking Service needs to support external ID management for entities. Currently, entities are identified internally by a system-generated UUID, but external systems (STARLIMS, HALO, Donor DB) need to reference entities by their own identifiers. This change implements the `register_external_id` and `supersede` operations on HippoClient to manage entity identification across systems, along with `get_by_external_id` for lookup.

The implementation builds on the existing entity model where entities have system fields (`id`, `is_available`) and the provenance log tracks temporal changes.

## Goals / Non-Goals

**Goals:**
- Implement `register_external_id(entity_id, external_id)` to associate an external ID with an existing entity
- Implement `supersede(entity_id, old_external_id, new_external_id)` to replace an entity's external ID while preserving history
- Implement `get_by_external_id(external_id)` to retrieve an entity by its external identifier
- Handle conflicts where external IDs may be associated with multiple entities over time (latest timestamp wins)
- Ensure external ID operations work with the existing availability model (only `active` entities should be returned by default)

**Non-Goals:**
- Automatic external ID migration from legacy systems (future work)
- Bulk registration operations (single-item only)
- External ID validation or format enforcement (delegated to external systems)
- Cross-system ID resolution (FAIR identification)

## Decisions

### 1. External ID Storage: Separate Table with Foreign Key to Entity

**Decision:** Store external IDs in a separate `entity_external_ids` table with a foreign key to the main entity table, rather than as a JSON field on the entity.

**Rationale:** This approach:
- Allows efficient lookups by external ID (indexed column)
- Prevents entity table bloat
- Enables easy querying of all external IDs for an entity
- Aligns with the relational model already established

**Alternative Considered:** JSON column on entity - rejected due to query performance and index limitations.

### 2. Supersede Preserves History

**Decision:** The `supersede` operation marks the old external ID as `superseded` in the provenance log rather than deleting it.

**Rationale:**
- Maintains full audit trail of external ID changes
- Allows historical lookups if needed
- Enables the "latest wins" behavior for `get_by_external_id`

### 3. External ID Uniqueness: Soft Conflict

**Decision:** Allow multiple entities to share the same external ID at different points in time, but `get_by_external_id` returns only the latest (by `created_at` timestamp).

**Rationale:** This matches real-world scenarios where external systems may reassign IDs. The temporal resolution ensures deterministic behavior.

**Alternative Considered:** Hard uniqueness constraint - rejected because it doesn't match real-world usage patterns.

### 4. Query Scope: Active Entities Only

**Decision:** `get_by_external_id` returns only entities where `is_available = true` by default.

**Rationale:** Matches the existing pattern for entity queries. Can add optional parameter for historical lookups in future.

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|------|--------|------------|
| Race condition on concurrent registrations | Medium | Use database-level locking or optimistic concurrency |
| Performance with many external IDs per entity | Low | Index on (external_id, created_at) for efficient latest-lookup |
| External ID orphaned on entity delete | Medium | Cascade delete external IDs when entity is marked deleted |

## Migration Plan

1. **Add new table** `entity_external_ids` with columns: `id`, `entity_id`, `external_id`, `created_at`, `superseded_at`
2. **Add new index** on `(external_id, created_at DESC)` for efficient latest-lookup
3. **Deploy** new code with new table
4. **No data migration needed** - new functionality only
5. **Rollback**: If issues arise, rollback code; table can be dropped if unused

## Open Questions

- Should `get_by_external_id` accept an optional parameter to include `archived` entities?
- Do we need to support external ID expiration (time-based invalidation)?
