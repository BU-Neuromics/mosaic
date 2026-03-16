## ADDED Requirements

### Requirement: WriteValidator ABC enforces validate method
A validator class that inherits from WriteValidator MUST implement the validate method or raise an exception during instantiation.

#### Scenario: Concrete validator without validate method
- **WHEN** a class inherits from WriteValidator without implementing validate
- **THEN** TypeError is raised during instantiation

#### Scenario: Concrete validator with validate method
- **WHEN** a class inherits from WriteValidator and implements validate
- **THEN** the class can be instantiated successfully

### Requirement: WriteValidator validate returns ValidationResult
WriteValidator validate method SHALL return a ValidationResult object.

#### Scenario: Validate with valid input
- **WHEN** validate is called with valid input meeting all rules
- **THEN** it returns a ValidationResult with success=true

#### Scenario: Validate with invalid input
- **WHEN** validate is called with input failing validation rules
- **THEN** it returns a ValidationResult with success=false and error details in errors

#### Scenario: Validate with null input
- **WHEN** validate is called with null or empty input
- **THEN** it returns a ValidationResult with success=false and clear error message

### Requirement: WriteOperation dataclass instantiation
WriteOperation MUST be a dataclass with required fields for operation data.

#### Scenario: Valid WriteOperation creation
- **WHEN** WriteOperation is instantiated with valid parameters
- **THEN** all fields are correctly assigned and accessible

#### Scenario: Missing required fields
- **WHEN** WriteOperation is instantiated with missing required fields
- **THEN** TypeError is raised during instantiation

### Requirement: ValidationResult dataclass
ValidationResult MUST be a dataclass containing validation outcome data.

#### Scenario: Successful validation result
- **WHEN** ValidationResult is instantiated with success=true and empty errors
- **THEN** success is True and errors is accessible as empty list

#### Scenario: Failed validation result
- **WHEN** ValidationResult is instantiated with success=false and error strings
- **THEN** success is False and errors contains the error messages

#### Scenario: Invalid parameters
- **WHEN** ValidationResult is instantiated with invalid parameters (e.g., non-iterable errors)
- **THEN** TypeError is raised during instantiation