## ADDED Requirements

### Requirement: Non-nullable column handling
The system SHALL handle adding non-nullable columns to tables with existing data appropriately.

#### Scenario: Add non-nullable column with default value
- **GIVEN** a user has a database with existing data
- **AND** they add a non-nullable column with a default value to a table
- **WHEN** they run `hippo migrate`
- **THEN** the system generates a migration that includes DEFAULT clause
- **AND** existing rows receive the default value
- **AND** the migration succeeds

#### Scenario: Add non-nullable column without default warns user
- **GIVEN** a user has a database with existing data
- **AND** they add a non-nullable column without a default value to a table
- **WHEN** they run `hippo migrate`
- **THEN** the system warns the user about the potential issue
- **AND** the migration is not applied without user confirmation or manual intervention

#### Scenario: Add nullable column to table with data
- **GIVEN** a user adds an optional (nullable) column to a table with existing rows
- **WHEN** they run `hippo migrate`
- **THEN** the migration is generated and applied successfully
- **AND** existing rows have NULL for the new column
