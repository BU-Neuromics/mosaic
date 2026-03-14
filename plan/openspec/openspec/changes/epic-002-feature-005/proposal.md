# SQLite Indexes and Summary Views

## Goal
SQLite Indexes and Summary Views: Implement partial indexes and summary views for improved query performance.

## Acceptance Criteria
- Given a database table with multiple rows, when a partial index is created on a filtered column, then queries filtering on that column execute 30% faster than without the index
- Given a summary view is defined with aggregated data, when a developer queries the view, then the aggregated statistics are returned within 100ms regardless of underlying table size
- Given a table has multiple indexes including partial indexes, when a query scans the table with filtered conditions, then only the relevant partial index is used tooptimize the query execution plan
- Given a database with existing data, when applying a partial index strategy to frequently queried columns, then query performance improves by at least 40% as measured by execution time reduction
- Given summary views are implemented, when multiple aggregation functions (count, sum, avg) are applied in the view definition, then all aggregated results are computed efficiently without redundant calculations

## Constraints
- Complexity: medium
