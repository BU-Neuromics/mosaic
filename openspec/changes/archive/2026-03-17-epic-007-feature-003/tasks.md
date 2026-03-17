## 1. Schema Diff Engine Implementation

- [x] 1.1 Implement SchemaDiffEngine class in src/hippo/core/storage/schema_diff.py
- [x] 1.2 Add method to load existing table metadata from SQLite
- [x] 1.3 Add method to load schema definitions from YAML files
- [x] 1.4 Implement diff algorithm to detect new tables
- [x] 1.5 Implement diff algorithm to detect new columns
- [x] 1.6 Implement diff algorithm to detect new indexes
- [x] 1.7 Implement diff algorithm to detect new constraints

## 2. Migration Plan Integration

- [x] 2.1 Update MigrationPlanner to accept schema diff output
- [x] 2.2 Generate ALTER TABLE statements for new columns
- [x] 2.3 Generate CREATE INDEX statements for new indexes
- [x] 2.4 Integrate with existing DDLGenerator for new tables
- [x] 2.5 Integrate with FTSMigrationPlanner for new FTS tables

## 3. CLI Integration

- [x] 3.1 Update hippo migrate command to load schemas from schemas/ directory
- [x] 3.2 Connect migrate command to SchemaDiffEngine
- [x] 3.3 Add --preview flag support (alias for --dry-run)
- [x] 3.4 Add --schema-dir option for custom schema path
- [x] 3.5 Add --db-path option for custom database path

## 4. Schema Validation

- [x] 4.1 Add validation for duplicate entity type definitions
- [x] 4.2 Add validation for invalid field types
- [x] 4.3 Add validation for broken references
- [x] 4.4 Integrate validation before diff generation

## 5. Non-nullable Column Handling

- [x] 5.1 Detect when adding non-nullable column to table with data
- [x] 5.2 Check for default value in schema definition
- [x] 5.3 Generate DDL with DEFAULT clause when available
- [x] 5.4 Add warning when no default and table has data

## 6. Preview Mode Output

- [x] 6.1 Display list of tables to be created/modified
- [x] 6.2 Display DDL statements that would be executed
- [x] 6.3 Display warning messages for risky operations
- [x] 6.4 Ensure no database modifications in preview mode

## 7. Testing

- [x] 7.1 Write unit tests for SchemaDiffEngine
- [x] 7.2 Write integration tests for migrate command
- [x] 7.3 Test preview mode output
- [x] 7.4 Test schema validation errors
- [x] 7.5 Test non-nullable column handling
