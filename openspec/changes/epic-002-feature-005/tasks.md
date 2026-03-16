## 1. Migration Infrastructure Updates

- [ ] 1.1 Add partial index creation logic to SQLite migration DDL generator
- [ ] 1.2 Update migration to detect `indexed: true` in field schema
- [ ] 1.3 Generate correct partial index SQL: `CREATE INDEX idx_{entity_type}_{field}_available ON {entity_type}s ({field}) WHERE is_available = true`
- [ ] 1.4 Add index creation to migration rollback functionality

## 2. Summary View Implementation

- [ ] 2.1 Create view generation module for SQLite adapter
- [ ] 2.2 Implement `summary_{entity_type}_count` view for active entity counts
- [ ] 2.3 Implement summary views with multiple aggregations (count, sum, avg)
- [ ] 2.4 Add view creation to migration system
- [ ] 2.5 Ensure views compute aggregations in single table scan

## 3. Query Integration

- [ ] 3.1 Update QueryEngine to use summary views for aggregation queries
- [ ] 3.2 Modify query patterns to filter by `is_available = true` for index usage
- [ ] 3.3 Add helper method for explaining query plans
- [ ] 3.4 Verify query planner selects partial indexes

## 4. Testing and Verification

- [ ] 4.1 Write unit tests for partial index creation
- [ ] 4.2 Write unit tests for summary view generation
- [ ] 4.3 Add integration tests for query performance (verify 30% improvement)
- [ ] 4.4 Add performance benchmarks for summary views (verify <100ms)
- [ ] 4.5 Verify 40% performance improvement on real queries
- [ ] 4.6 Test index usage with EXPLAIN QUERY PLAN
