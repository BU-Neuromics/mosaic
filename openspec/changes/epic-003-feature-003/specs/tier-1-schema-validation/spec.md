## ADDED Requirements

### Requirement: Required field validation
The system SHALL validate that all required fields are present in write operations.

#### Scenario: Missing required field
- **WHEN** a write operation contains a required field missing
- **THEN** ValidationResult indicates the missing field with error message "Field 'fieldName' is required"

#### Scenario: All required fields present
- **WHEN** a write operation contains all required fields
- **THEN** ValidationResult does not include any required field errors

### Requirement: Type constraint validation
The system SHALL validate that field values match the declared type in the schema.

#### Scenario: Invalid string type
- **WHEN** a write operation has invalid data type for a string field
- **THEN** ValidationResult indicates type mismatch with expected type information "Expected string type for field 'fieldName'"

#### Scenario: Invalid number type
- **WHEN** a write operation has invalid data type for a number field
- **THEN** ValidationResult indicates type mismatch with expected type information "Expected number type for field 'fieldName'"

#### Scenario: Invalid boolean type
- **WHEN** a write operation has invalid boolean value
- **THEN** ValidationResult indicates type mismatch with expected type information "Expected boolean type for field 'fieldName'"

#### Scenario: Invalid timestamp format
- **WHEN** a write operation has invalid timestamp format
- **THEN** ValidationResult indicates type mismatch with expected type information "Expected ISO 8601 timestamp format for field 'fieldName'"

### Requirement: Reference existence validation
The system SHALL validate that referenced entity IDs exist in the system.

#### Scenario: Non-existent entity reference
- **WHEN** a write operation references a non-existent entity ID
- **THEN** ValidationResult indicates reference error with reference information "Reference to non-existent entity 'entityType' with ID 'entityId'"

#### Scenario: Nested object reference error
- **WHEN** a write operation references a non-existent entity with nested object
- **THEN** ValidationResult indicates reference error with nested reference information "Reference to non-existent entity 'entityType' in field 'nested.field'"

#### Scenario: Valid entity reference
- **WHEN** a write operation references an existing entity ID
- **THEN** ValidationResult does not include any reference errors for that field

### Requirement: Enum validation
The system SHALL validate that enum field values are from the allowed set.

#### Scenario: Invalid enum value
- **WHEN** a write operation has invalid enum value
- **THEN** ValidationResult indicates enum validation error with expected values "Invalid enum value 'value' for field 'fieldName'. Expected one of [valid, values]"

#### Scenario: Valid enum value
- **WHEN** a write operation has a valid enum value from the allowed set
- **THEN** ValidationResult does not include any enum validation errors

### Requirement: Multiple validation errors
The system SHALL collect and report multiple validation errors in a single ValidationResult.

#### Scenario: Multiple validation failures
- **WHEN** a write operation contains multiple validation errors
- **THEN** ValidationResult contains all errors in a list format

### Requirement: Successful validation
The system SHALL indicate successful validation when all checks pass.

#### Scenario: Valid write operation
- **WHEN** a write operation has valid data and passes all validations
- **THEN** ValidationResult indicates success with no errors