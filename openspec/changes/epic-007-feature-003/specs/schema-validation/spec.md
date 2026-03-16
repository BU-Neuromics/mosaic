## ADDED Requirements

### Requirement: Schema validation before migration
The system SHALL validate schema definitions before generating migrations to ensure consistency and prevent invalid migrations.

#### Scenario: Conflicting schema definitions are detected
- **GIVEN** a user runs `hippo migrate` with conflicting schema definitions
- **WHEN** the system detects inconsistencies
- **THEN** it properly reports errors and does not generate invalid migrations

#### Scenario: Duplicate entity type definitions
- **GIVEN** the same entity type is defined multiple times in schema files
- **WHEN** `hippo migrate` is executed
- **THEN** the system reports a conflict error
- **AND** no migrations are generated

#### Scenario: Invalid field type in schema
- **GIVEN** a schema file contains an invalid field type
- **WHEN** `hippo migrate` is executed
- **THEN** the system reports a validation error
- **AND** migration is aborted

#### Scenario: Invalid reference in schema
- **GIVEN** a schema field references a non-existent entity type
- **WHEN** `hippo migrate` is executed
- **THEN** the system reports a validation error with the specific reference issue
- **AND** migration is aborted
