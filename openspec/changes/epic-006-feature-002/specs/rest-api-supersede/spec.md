## ADDED Requirements

### Requirement: POST /entities/{id}/supersede creates superseding entity
The system SHALL return HTTP 200 status code with the new superseding entity when a client makes a POST request to /entities/{id}/supersede endpoint with the new entity data.

#### Scenario: Supersede an entity
- **WHEN** a client makes a POST request to /entities/{id}/supersede endpoint with new entity data
- **THEN** the server creates a new entity that supersedes the original and returns HTTP 200 with the new entity

### Requirement: GET /entities/{id}/superseded returns superseded entities
The system SHALL return HTTP 200 status code with a list of entities that have been superseded by the given entity when a client makes a GET request to /entities/{id}/superseded endpoint.

#### Scenario: Get superseded entities
- **WHEN** a client makes a GET request to /entities/{id}/superseded endpoint
- **THEN** the server returns HTTP 200 status code with a list of entities that this entity supersedes
