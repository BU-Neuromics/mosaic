## ADDED Requirements

### Requirement: Schema validation accepts valid data
Given a write operation with all required fields populated correctly, when the validation logic is executed, then the operation shall complete successfully with no validation errors.

#### Scenario: Write entity with all required fields
- **WHEN** client writes an entity with all required fields populated correctly
- **THEN** operation completes successfully
- **AND** entity is persisted in storage
- **AND** no validation errors are returned

### Requirement: Schema validation rejects missing required fields
Given a write operation missing a required field, when the validation logic is executed, then the operation shall fail with a clear error message indicating the missing field and its expected data type.

#### Scenario: Write entity missing required string field
- **WHEN** client attempts to write an entity without a required string field
- **THEN** operation fails
- **AND** error indicates the missing field name
- **AND** error indicates expected data type is string

#### Scenario: Write entity missing required integer field
- **WHEN** client attempts to write an entity without a required integer field
- **THEN** operation fails
- **AND** error indicates the missing field name
- **AND** error indicates expected data type is integer

### Requirement: Schema validation rejects invalid foreign key references
Given a write operation referencing a non-existent entity in a foreign key field, when the validation logic is executed, then the operation shall fail with an appropriate reference error detailing the invalid relationship.

#### Scenario: Write entity with invalid foreign key reference
- **WHEN** client attempts to write an entity with a foreign key field referencing a non-existent entity ID
- **THEN** operation fails
- **AND** error indicates invalid reference
- **AND** error identifies the field with the invalid reference

### Requirement: Schema validation rejects invalid data types
Given a write operation containing invalid data types in fields (e.g., string in numeric field), when the validation logic is executed, then the operation shall fail with specific error messages identifying the problematic field and expected data type.

#### Scenario: Write string in numeric field
- **WHEN** client attempts to write a string value in a field defined as integer
- **THEN** operation fails
- **AND** error identifies the problematic field
- **AND** error indicates expected data type is integer

#### Scenario: Write integer in string field
- **WHEN** client attempts to write an integer value in a field defined as string
- **THEN** operation fails
- **AND** error identifies the problematic field
- **AND** error indicates expected data type is string

### Requirement: Schema validation rejects data exceeding constraints
Given a write operation with valid data that exceeds length or size constraints, when the validation logic is executed, then the operation shall fail with an appropriate constraint violation error specifying the exceeded limit.

#### Scenario: Write string exceeding max length
- **WHEN** client attempts to write a string that exceeds the defined max_length constraint
- **THEN** operation fails
- **AND** error indicates the constraint violation
- **AND** error specifies the maximum allowed length

#### Scenario: Write array exceeding max items
- **WHEN** client attempts to write an array that exceeds the defined max_items constraint
- **THEN** operation fails
- **AND** error indicates the constraint violation
- **AND** error specifies the maximum allowed items
