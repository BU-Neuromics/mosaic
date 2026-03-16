## ADDED Requirements

### Requirement: ConfigError raised for invalid YAML syntax
When the config loader attempts to parse a hippo.yaml file with invalid YAML syntax, the system SHALL raise a ConfigError with a message indicating "invalid YAML syntax".

#### Scenario: Invalid YAML syntax in config file
- **WHEN** a hippo.yaml file contains invalid YAML syntax
- **AND** the config loader attempts to parse it
- **THEN** a ConfigError is raised with a message containing "invalid YAML syntax"

### Requirement: ConfigError raised for missing required fields
When the config loader validates a hippo.yaml file with missing required fields, the system SHALL raise a ConfigError with a message identifying the missing field.

#### Scenario: Missing required field in config
- **WHEN** a hippo.yaml file is missing a required field
- **AND** the config loader validates it
- **THEN** a ConfigError is raised with a message identifying the missing field name

### Requirement: SchemaError raised for invalid JSON Schema definition
When the schema parser processes a schema.yaml with an invalid JSON Schema definition, the system SHALL raise a SchemaError with a message specifying the parsing error location and description.

#### Scenario: Invalid schema definition
- **WHEN** a schema.yaml contains an invalid JSON Schema definition
- **AND** the schema parser attempts to process it
- **THEN** a SchemaError is raised with a message specifying the error location and description

### Requirement: EntityNotFoundError raised for non-existent entity
When an operation processes an entity that does not exist in the system, the system SHALL raise an EntityNotFoundError with a message indicating the resource name and ID.

#### Scenario: Accessing non-existent entity
- **WHEN** an operation attempts to access an entity that does not exist
- **AND** the entity ID is not found in the system
- **THEN** an EntityNotFoundError is raised with a message indicating the resource type and ID

### Requirement: AdapterError raised for invalid adapter configuration
When an adapter encounters an invalid configuration during initialization, the system SHALL raise an AdapterError with details about the misconfiguration.

#### Scenario: Invalid adapter configuration
- **WHEN** an adapter is initialized with invalid configuration
- **AND** the adapter attempts to load its settings
- **THEN** an AdapterError is raised with details about the misconfiguration
