## MODIFIED Requirements

### Requirement: Schema Validation
The system SHALL allow users to validate schema files against defined rules using the `hippo validate --schema <file>` command. When a user provides a valid schema file, all validation rules defined for the schema SHALL be applied — including namespace graph validation — and return a success status code with no errors reported.

#### Scenario: Valid schema validation
- **WHEN** user runs `hippo validate --schema <file>` with a valid JSON/YAML schema file
- **THEN** system applies all validation rules (including namespace resolution and cross-namespace reference checks) and returns a success status code with no errors

#### Scenario: Valid multi-file namespace schema passes validation
- **WHEN** user runs `hippo validate --schema` against a schema directory containing files with `namespace` keys and valid cross-namespace references
- **THEN** system resolves the namespace graph, validates all cross-namespace references, and returns a success status code

### Requirement: Validation Error Reporting
The system SHALL report specific validation errors when users run the validator on schema files with validation errors. The error messages SHALL clearly indicate the location and nature of each violation, including namespace errors such as unknown references, duplicate entities, and circular dependencies.

#### Scenario: Invalid schema validation
- **WHEN** user runs `hippo validate --schema <file>` with a schema file containing validation errors
- **THEN** system reports specific validation errors with clear error messages indicating the location and nature of each violation

#### Scenario: Unknown cross-namespace reference error is reported
- **WHEN** user runs `hippo validate --schema` on a schema containing a `references.entity_type` pointing to a namespace or entity that does not exist
- **THEN** system reports a `SchemaValidationError` identifying the unresolved FQN reference and the file where it appears

#### Scenario: Circular namespace dependency error is reported
- **WHEN** user runs `hippo validate --schema` on a schema set where two namespaces reference each other in a cycle
- **THEN** system reports a `SchemaValidationError` identifying the circular dependency path
