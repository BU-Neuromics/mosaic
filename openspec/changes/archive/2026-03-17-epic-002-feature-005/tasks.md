## 1. Migration Infrastructure Updates

- [x] 1.1 Add partial index creation logic to SQLite migration DDL generator
- [x] 1.2 Update migration to detect `indexed: true` in field schema
- [x] 1.3 Generate correct partial index SQL: `CREATE INDEX idx_{entity_type}_{field}_available ON {entity_type}s ({field}) WHERE is_available = true`
- [x] 1.4 Add index creation to migration rollback functionality

## 2. Summary View Implementation

- [x] 2.1 Create view generation module for SQLite adapter
- [x] 2.2 Implement `summary_{entity_type}_count` view for active entity counts
- [x] 2.3 Implement summary views with multiple aggregations (count, sum, avg)
- [x] 2.4 Add view creation to migration system
- [x] 2.5 Ensure views compute aggregations in single table scan

## 3. Query Integration

- [x] 3.1 Update QueryEngine to use summary views for aggregation queries
- [x] 3.2 Modify query patterns to filter by `is_available = true` for index usage
- [x] 3.3 Add helper method for explaining query plans
- [x] 3.4 Verify query planner selects partial indexes

## 4. Testing and Verification

- [x] 4.1 Write unit tests for partial index creation
- [x] 4.2 Write unit tests for summary view generation
- [x] 4.3 Add integration tests for query performance (verify 30% improvement)
- [x] 4.4 Add performance benchmarks for summary views (verify <100ms)
- [x] 4.5 Verify 40% performance improvement on real queries
- [x] 4.6 Test index usage with EXPLAIN QUERY PLAN
