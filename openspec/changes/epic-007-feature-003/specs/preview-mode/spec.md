## ADDED Requirements

### Requirement: Preview mode
The system SHALL support a preview mode that outputs planned migration actions without applying them.

#### Scenario: Preview mode shows planned migrations
- **GIVEN** a user runs `hippo migrate --preview`
- **WHEN** they request preview mode
- **THEN** the system outputs the planned migration actions without applying them
- **AND** the database remains unchanged

#### Scenario: Preview mode with --dry-run flag
- **GIVEN** a user runs `hippo migrate --dry-run`
- **WHEN** they request preview mode using the dry-run flag
- **THEN** the system outputs the planned migration actions without applying them
- **AND** the behavior is identical to `--preview`

#### Scenario: Preview shows all DDL statements
- **GIVEN** a schema with multiple changes
- **WHEN** `hippo migrate --preview` is executed
- **THEN** all DDL statements that would be executed are displayed
- **AND** no database modifications occur
