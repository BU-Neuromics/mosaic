# Schema Compilation and Validation

## Goal
Schema Compilation and Validation: Implement schema compilation and validation features that allow developers to compile and validate schemas through the CLI.

## Acceptance Criteria
- Given a user has a valid schema file in JSON format, when they run 'hippo compile-schema', then the CLI should successfully transform the schema into a system-readable format and output the compiled result to stdout
- Given a user has a schema file with syntax errors, when they run 'hippo compile-schema', then the CLI should display a clear error message indicating the location and type of syntax error in the schema file
- Given a user has a valid schema file, when they run 'hippo validate --schema <file>', then all validation rules defined for the schema should be applied and return a success status code with no errors reported
- Given a user has a schema file with validation errors, when they run 'hippo validate --schema <file>', then the CLI should report specific validation errors with clear error messages indicating the location and nature of each violation
- Given a user has two different schema versions in separate files, when they run 'hippo schema diff', then the CLI should detect and display all differences between the schemas in a human-readable format including added/removed/modified elements
- Given a user runs 'hippo schema diff' with invalid file paths, when they compare schemas, then the CLI should output an appropriate error message specifying which files could not be found or are invalid

## Constraints
- Depends on: feature-001
- Complexity: medium
