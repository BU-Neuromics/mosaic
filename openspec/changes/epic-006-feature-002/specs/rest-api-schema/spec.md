## ADDED Requirements

### Requirement: GET /schemas returns available schemas
The system SHALL return HTTP 200 status code with a JSON array of available schema configurations when a client makes a GET request to /schemas endpoint.

#### Scenario: List available schemas
- **WHEN** a client makes a GET request to /schemas endpoint
- **THEN** the server returns HTTP 200 status code with a JSON array of schema configurations

### Requirement: GET /schemas/{schema_name} returns schema details
The system SHALL return HTTP 200 status code with the schema configuration details when a client makes a GET request to /schemas/{schema_name} endpoint.

#### Scenario: Get schema details
- **WHEN** a client makes a GET request to /schemas/{schema_name} endpoint
- **THEN** the server returns HTTP 200 status code with the schema configuration details including entity types, fields, and relationships

### Requirement: POST /schemas creates new schema
The system SHALL return HTTP 201 status code with the created schema configuration when a client makes a POST request to /schemas endpoint.

#### Scenario: Create new schema
- **WHEN** a client makes a POST request to /schemas endpoint with schema configuration
- **THEN** the server returns HTTP 201 status code with the created schema configuration
