## ADDED Requirements

### Requirement: count_constraint preset validates collection count limits
The system SHALL validate that collection fields do not exceed the configured maximum count when using the count_constraint preset.

#### Scenario: Count constraint violation - exceeds limit
- **WHEN** validation runs on a collection with more items than the configured limit
- **THEN** system throws a count constraint violation error

#### Scenario: Count constraint satisfied - within limit
- **WHEN** validation runs on a collection with items within the configured limit
- **THEN** system accepts the document without any errors
