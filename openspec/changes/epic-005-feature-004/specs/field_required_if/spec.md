## ADDED Requirements

### Requirement: field_required_if preset enforces conditional field requirements
The system SHALL make fields required when specified conditions are met using the field_required_if preset.

#### Scenario: Field required condition met - field present
- **WHEN** validation runs and the required condition is met but the field is present
- **THEN** system accepts the document without any errors

#### Scenario: Field required condition met - field missing
- **WHEN** validation runs and the required condition is met but the field is missing
- **THEN** system rejects the document with a field required violation error

#### Scenario: Field required condition not met - field missing
- **WHEN** validation runs and the required condition is not met
- **THEN** system accepts the document without any errors
