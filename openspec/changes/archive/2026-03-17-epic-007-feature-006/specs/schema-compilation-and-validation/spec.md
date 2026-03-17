## ADDED Requirements

### Requirement: Schema Compilation
The system SHALL allow users to compile schema files from JSON format into a system-readable format using the 'hippo compile-schema' command. When a user provides a valid schema file, the CLI should successfully transform the schema and output the compiled result to stdout.

#### Scenario: Successful compilation
- **WHEN** user runs 'hippo compile-schema' with a valid JSON schema file
- **THEN** system outputs the compiled schema in a readable format to stdout

### Requirement: Syntax Error Handling
The system SHALL display a clear error message when a user attempts to compile a schema file with syntax errors. The error message should indicate the location and type of syntax error in the schema file.

#### Scenario: Invalid JSON syntax
- **WHEN** user runs 'hippo compile-schema' with a schema file containing invalid JSON syntax
- **THEN** system displays an appropriate error message indicating the file path, line number, and syntax error type

### Requirement: Schema Validation
The system SHALL allow users to validate schema files against defined rules using the 'hippo validate --schema <file>' command. When a user provides a valid schema file, all validation rules defined for the schema should be applied and return a success status code with no errors reported.

#### Scenario: Valid schema validation
- **WHEN** user runs 'hippo validate --schema <file>' with a valid JSON schema file
- **THEN** system applies all validation rules and returns a success status code with no errors

### Requirement: Validation Error Reporting
The system SHALL report specific validation errors when users run the validator on schema files with validation errors. The error messages should clearly indicate the location and nature of each violation.

#### Scenario: Invalid schema validation
- **WHEN** user runs 'hippo validate --schema <file>' with a schema file containing validation errors  
- **THEN** system reports specific validation errors with clear error messages indicating the location and nature of each violation

### Requirement: Schema Diff Functionality
The system SHALL allow users to compare two different schema versions using the 'hippo schema diff' command. When users provide file paths for two different schema versions, the CLI should detect and display all differences between the schemas in a human-readable format.

#### Scenario: Schema comparison with valid files
- **WHEN** user runs 'hippo schema diff <file1> <file2>' with valid schema files  
- **THEN** system detects and displays all differences including added/removed/modified elements in a human-readable format

### Requirement: Invalid File Path Handling
The system SHALL output an appropriate error message when users run 'hippo schema diff' with invalid file paths. The error should specify which files could not be found or are invalid.

#### Scenario: Missing file during diff
- **WHEN** user runs 'hippo schema diff <file1> <file2>' with one or both files not existing
- **THEN** system outputs an appropriate error message specifying which files could not be found or are invalid
