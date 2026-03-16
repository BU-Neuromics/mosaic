## ADDED Requirements

### Requirement: Partial index creation for indexed fields
The SQLite storage adapter SHALL create partial indexes on fields marked with `indexed: true` in the schema configuration, scoped to `is_available = true`.

#### Scenario: Partial index created on indexed field
- **WHEN** a field is defined in schema with `indexed: true`
- **THEN** the migration system SHALL create a partial index with SQL: `CREATE INDEX idx_{entity_type}_{field}_available ON {entity_type}s ({field}) WHERE is_available = true`

#### Scenario: Partial index used in query execution
- **WHEN** a query filters on an indexed field with `is_available = true`
- **THEN** the SQLite query planner SHALL select the partial index to optimize execution

#### Scenario: Partial index improves query performance
- **WHEN** a partial index exists on a frequently queried column
- **THEN** queries filtering on that column SHALL execute at least 30% faster than without the index

### Requirement: Summary view creation for entity aggregations
The SQLite storage adapter SHALL create summary views for common aggregation patterns on each entity type.

#### Scenario: Count summary view exists
- **WHEN** a developer queries `summary_{entity_type}_count` view
- **THEN** the view SHALL return the count of active entities of that type

#### Scenario: Summary view returns within performance threshold
- **WHEN** a summary view is queried
- **THEN** the aggregated statistics SHALL be returned within 100ms regardless of underlying table size

#### Scenario: Multiple aggregation functions in single view
- **WHEN** a summary view is defined with count, sum, and avg aggregations
- **THEN** all aggregated results SHALL be computed efficiently without redundant table scans

### Requirement: Query planner optimization for partial indexes
The SQLite storage adapter SHALL ensure the query planner correctly identifies and uses relevant partial indexes.

#### Scenario: Query uses partial index for filtered conditions
- **WHEN** a query includes `WHERE is_available = true` and filters on an indexed field
- **THEN** the query execution plan SHALL show only the relevant partial index is used

#### Scenario: Partial index used across multiple entity queries
- **WHEN** multiple entity types have partial indexes on commonly filtered fields
- **THEN** each entity type's queries SHALL utilize their respective partial indexes independently

### Requirement: Performance measurement and verification
The implementation SHALL include mechanisms to verify performance improvements from indexes and views.

#### Scenario: Performance improvement measurement
- **WHEN** partial index strategy is applied to frequently queried columns
- **THEN** query performance SHALL improve by at least 40% as measured by execution time reduction

#### Scenario: Index usage verification
- **WHEN** a developer needs to verify index usage
- **THEN** the system SHALL provide a way to inspect query execution plans (e.g., via `EXPLAIN QUERY PLAN`)

### Requirement: Summary view refresh mechanism
The summary views SHALL maintain accurate data through an appropriate refresh strategy.

#### Scenario: View data refresh on read
- **WHEN** a summary view is queried
- **THEN** the view SHALL return current, accurate aggregated data reflecting all committed transactions

#### Scenario: Multiple aggregation functions computed efficiently
- **WHEN** a summary view includes count, sum, and avg functions on the same dataset
- **THEN** the database SHALL compute all aggregations in a single table scan to avoid redundant calculations
