## ADDED Requirements

### Requirement: Migration plan generation
The system SHALL generate migration plans that include all necessary DDL statements for applying schema changes.

#### Scenario: Generate migration plan for new table
- **GIVEN** a schema with a new entity type defined
- **WHEN** `hippo migrate` is executed
- **THEN** the migration plan includes CREATE TABLE statements for the new entity

#### Scenario: Generate migration plan for new column
- **GIVEN** a schema adds a new field to an existing entity type
- **WHEN** `hippo migrate` is executed
- **THEN** the migration plan includes ALTER TABLE ADD COLUMN statements

#### Scenario: Generate migration plan for new FTS table
- **GIVEN** a schema defines a new field with search fts enabled
- **WHEN** `hippo migrate` is executed
- **THEN** the migration plan includes FTS5 virtual table creation statements

### Requirement: Migration execution
The system SHALL execute migration plans and report success or failure.

#### Scenario: Migration executes successfully
- **GIVEN** a valid migration plan exists
- **WHEN** `hippo migrate` is executed (not in preview mode)
- **THEN** all DDL statements are applied to the database
- **AND** the system reports the number of tables/columns created

#### Scenario: Migration reports no changes needed
- **GIVEN** a database that already matches the schema
- **WHEN** `hippo migrate` is executed
- **THEN** the system reports that no migrations are needed
- **AND** no database changes are made
