## ADDED Requirements

### Requirement: HippoConfig model loads valid hippo.yaml with environment variable substitution
The system SHALL load a hippo.yaml file and substitute environment variables in the format ${VAR} with their corresponding system values.

#### Scenario: Valid YAML with environment variables loads correctly
- **WHEN** a valid hippo.yaml file contains ${DATABASE_HOST} and ${DATABASE_PORT} placeholders
- **AND** the environment variables DATABASE_HOST and DATABASE_PORT are defined in the system
- **THEN** the HippoConfig model is instantiated with the substituted values

#### Scenario: Environment variable not defined raises ConfigError
- **WHEN** a hippo.yaml file contains an ${UNDEFINED_VAR} placeholder
- **AND** UNDEFINED_VAR is not defined in the system environment
- **THEN** a ConfigError is raised with a message indicating the undefined variable name

### Requirement: HippoConfig model validates required fields
The system SHALL raise a ConfigError when hippo.yaml is missing required fields.

#### Scenario: Missing required field raises ConfigError
- **WHEN** a hippo.yaml file omits a required field (e.g., schema_path)
- **AND** the loader processes the file
- **THEN** a ConfigError is raised with a clear message indicating the missing field name

### Requirement: HippoConfig model validates field data types
The system SHALL raise a ValidationError when hippo.yaml contains incorrect data types for fields.

#### Scenario: Incorrect type raises ValidationError
- **WHEN** a hippo.yaml file has an integer field (e.g., port) set to a string value "abc"
- **AND** the loader processes the file
- **THEN** a ValidationError is raised with descriptive information about the type mismatch

### Requirement: Valid YAML without environment variables loads with exact values
The system SHALL load a hippo.yaml file without environment variables using the exact values specified.

#### Scenario: No environment variables loads exact values
- **WHEN** a valid hippo.yaml file contains no environment variable placeholders
- **AND** the loader processes the file
- **THEN** the HippoConfig model contains the exact values from the file

### Requirement: ConfigError provides actionable error messages
The system SHALL provide clear, actionable error messages for configuration errors.

#### Scenario: ConfigError message includes field name
- **WHEN** a required field is missing from hippo.yaml
- **THEN** the ConfigError message includes the name of the missing field

#### Scenario: ValidationError message includes type information
- **WHEN** a field has an incorrect type
- **THEN** the ValidationError message includes the expected type and actual value