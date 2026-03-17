## ADDED Requirements

### Requirement: immutable_field preset prevents field modification
The system SHALL reject attempts to modify fields marked as immutable using the immutable_field preset.

#### Scenario: Immutable field violation - field modification attempted
- **WHEN** validation runs on a document that attempts to modify an immutable field
- **THEN** system rejects the change with an immutable field violation error

#### Scenario: Immutable field satisfied - no modification
- **WHEN** validation runs on a document where immutable fields remain unchanged
- **THEN** system accepts the document without any errors
