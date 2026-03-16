## ADDED Requirements

### Requirement: Expand Path Parser SHALL identify all referenced fields
The expand path parser SHALL correctly identify all referenced fields and their parent-child relationships from a complex expand path string.

#### Scenario: Complex nested path with multiple levels
- **WHEN** parser processes "user.profile.settings"
- **THEN** it correctly identifies fields: user → profile → settings with parent-child associations

#### Scenario: Multiple entity references
- **WHEN** parser processes "orders.items.product"
- **THEN** it correctly identifies: orders → items → product with proper entity relationships

#### Scenario: Multiple nested levels with same field names
- **WHEN** parser processes "user.profile.settings.name" and "user.settings.name"
- **THEN** it correctly resolves field uniqueness and hierarchy without ambiguity

#### Scenario: Malformed path with empty segment
- **WHEN** parser processes "user..profile"
- **THEN** it throws a ParsingError with descriptive error message indicating invalid syntax

### Requirement: Batch Fetcher SHALL optimize database queries
The batch fetcher SHALL perform only one database query per entity list instead of N individual queries for each entity type.

#### Scenario: Multiple entity references with batching
- **WHEN** batch fetcher executes for "orders.items.product"
- **THEN** it performs one query for orders, one query for items, one query for product (3 queries total, not N)

#### Scenario: Simple single-level path
- **WHEN** batch fetcher executes for "user.name"
- **THEN** it correctly fetches the referenced field in a single database query without batching

#### Scenario: Complex multi-entity nested path
- **WHEN** batch fetcher executes for "user.orders.items.product.category"
- **THEN** it performs optimized database queries with appropriate grouping per entity type

### Requirement: Cycle Detector SHALL detect circular references
The cycle detector SHALL detect cycles in expand paths and throw a CycleDetectionError with specific error message indicating the cycle path.

#### Scenario: Circular reference detection
- **WHEN** validation occurs on "user.orders.items.user"
- **THEN** it detects the cycle and throws CycleDetectionError with message indicating the cycle path

#### Scenario: Valid path with no cycles
- **WHEN** cycle detector executes on "user.orders.items.product"
- **THEN** it correctly identifies no cycles and allows query execution to proceed

### Requirement: Max Size Enforcer SHALL validate path length
The max size enforcer SHALL validate expand path length and throw MaxSizeExceededError when the path exceeds the configured limit.

#### Scenario: Path exceeds maximum size
- **WHEN** parser processes an expand path longer than 100 characters
- **THEN** it throws MaxSizeExceededError with clear error message specifying the limit and actual size

#### Scenario: Path at exactly maximum size
- **WHEN** parser processes an expand path exactly at 100 characters
- **THEN** it successfully validates without throwing MaxSizeExceededError
