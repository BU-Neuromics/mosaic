## ADDED Requirements

### Requirement: ref_check preset validates reference constraints
The system SHALL validate that referenced entities exist when using the ref_check preset with a reference constraint.

#### Scenario: Reference constraint violation - invalid reference
- **WHEN** validation runs on a document with a reference to a non-existent entity
- **THEN** system rejects the document with a reference constraint violation error

#### Scenario: Reference constraint satisfied - valid reference
- **WHEN** validation runs on a document with a valid reference to an existing entity
- **THEN** system accepts the document without any errors
