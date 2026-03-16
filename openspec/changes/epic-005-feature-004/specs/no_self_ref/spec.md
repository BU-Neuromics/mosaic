## ADDED Requirements

### Requirement: no_self_ref preset prevents self-references
The system SHALL reject documents that contain self-references when using the no_self_ref preset.

#### Scenario: Self-reference violation - document references itself
- **WHEN** validation runs on a document that references itself
- **THEN** system rejects the document with a self-reference violation error

#### Scenario: Self-reference satisfied - no self-reference
- **WHEN** validation runs on a document without self-references
- **THEN** system accepts the document without any errors
