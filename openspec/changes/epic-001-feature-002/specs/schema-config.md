# SchemaConfig Specification

## ADDED Requirements

### Requirement: SchemaConfig Pydantic Model
The system SHALL provide a SchemaConfig Pydantic model that represents the structure of Hippo DSL schema files with all necessary validation.

#### Scenario: Valid schema with proper base inheritance
- **WHEN** the parser processes a valid schema.yaml file with proper base inheritance
- **THEN** the schema is successfully parsed into a SchemaConfig model with all fields correctly populated

### Requirement: Base Inheritance Cycle Detection
The system SHALL detect circular base inheritance in schema files and raise appropriate errors with clear messages.

#### Scenario: Single schema circular inheritance
- **WHEN** the parser processes a schema.yaml file with circular base inheritance within a single schema
- **THEN** a SchemaError is raised with message containing "circular inheritance" and error code "CYCLE_DETECTED"

#### Scenario: Multi-schema circular inheritance
- **WHEN** the parser processes a schema.yaml file with inheritance cycle involving multiple schemas
- **THEN** a SchemaError is raised with error code "CIRCULAR_INHERITANCE" indicating the complete cycle path detected

### Requirement: Schema Field Validation
The system SHALL validate schema files for required fields, types, and field uniqueness.

#### Scenario: Missing required fields
- **WHEN** the parser processes an invalid schema.yaml file with missing required fields
- **THEN** appropriate validation errors are raised with clear error messages indicating the missing fields

#### Scenario: Invalid field types
- **WHEN** the parser processes a schema.yaml file with invalid field types
- **THEN** appropriate validation errors are raised with clear error messages indicating the invalid field types

#### Scenario: Duplicate field names
- **WHEN** the parser processes a schema.yaml file with duplicate field names across inheritance hierarchy
- **THEN** appropriate validation errors are raised with clear error messages indicating the duplicate field definition

### Requirement: YAML Syntax Validation
The system SHALL handle malformed YAML syntax with clear error messages.

#### Scenario: Malformed YAML syntax
- **WHEN** the parser processes a schema.yaml file with malformed YAML syntax
- **THEN** a YAML parsing error is raised with clear error message indicating the syntax issue location

### Requirement: Base Reference Validation
The system SHALL validate that base references point to existing schemas.

#### Scenario: Non-existent base reference
- **WHEN** the parser processes a schema.yaml file with base reference to non-existent schema
- **THEN** a SchemaError is raised with message containing "undefined base" and error code "BASE_NOT_FOUND"

### Requirement: Deep Inheritance Chain Support
The system SHALL support valid inheritance chains of more than 3 levels.

#### Scenario: Deep inheritance chain (>3 levels)
- **WHEN** the parser processes a schema.yaml file with valid inheritance chain of more than 3 levels
- **THEN** the schema is successfully parsed into a SchemaConfig model maintaining proper inheritance resolution

### Requirement: Nested Inheritance Resolution
The system SHALL correctly resolve nested inheritance structures with multiple inheritance paths.

#### Scenario: Nested inheritance with multiple paths
- **WHEN** the parser processes a schema.yaml file with nested inheritance structures involving multiple inheritance paths
- **THEN** the schema is successfully parsed into a SchemaConfig model maintaining correct field resolution order
