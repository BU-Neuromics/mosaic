## ADDED Requirements

### Requirement: Schema diff detection
The system SHALL detect schema changes by comparing schema definition files against the existing database schema.

#### Scenario: Existing database with schema changes
- **GIVEN** a user has an existing database schema
- **WHEN** they run `hippo migrate`
- **THEN** the system detects schema changes and generates appropriate migration plans

#### Scenario: Empty database with no schema
- **GIVEN** a user runs `hippo migrate` on an empty database
- **WHEN** no schema changes are detected
- **THEN** the system reports that no migrations are needed

### Requirement: Additive change detection
The system SHALL identify additive schema changes including new tables, columns, and indexes.

#### Scenario: New table added to schema
- **GIVEN** a user modifies a schema definition by adding a new entity type
- **WHEN** they run `hippo migrate`
- **THEN** the additive change is properly identified as a new table creation migration step

#### Scenario: New column added to existing table
- **GIVEN** a user modifies a schema definition by adding a new field to an entity type
- **WHEN** they run `hippo migrate`
- **THEN** the additive change is properly identified as an ALTER TABLE ADD COLUMN migration step

#### Scenario: New index added to schema
- **GIVEN** a user modifies a schema definition by adding an index definition
- **WHEN** they run `hippo migrate`
- **THEN** the system properly identifies and includes the index creation in migration steps

### Requirement: Multi-element schema change detection
The system SHALL correctly identify all changes when multiple schema elements are modified in a single definition file.

#### Scenario: Multiple schema elements changed
- **GIVEN** a user modifies multiple schema elements in a single definition file
- **WHEN** they run `hippo migrate`
- **THEN** the system correctly identifies all changes and generates appropriate migration steps for each change
