## ADDED Requirements

### Requirement: GET /external-ids/{id_type}/{external_id} resolves external ID
The system SHALL return HTTP 200 status code with the associated entity when a client makes a GET request to /external-ids/{id_type}/{external_id} endpoint.

#### Scenario: Resolve external ID to entity
- **WHEN** a client makes a GET request to /external-ids/{id_type}/{external_id} endpoint
- **THEN** the server returns HTTP 200 status code with the entity associated with that external ID

### Requirement: GET /entities/{id}/external-ids returns entity external IDs
The system SHALL return HTTP 200 status code with a JSON array of external ID records when a client makes a GET request to /entities/{id}/external-ids endpoint.

#### Scenario: Get entity external IDs
- **WHEN** a client makes a GET request to /entities/{id}/external-ids endpoint
- **THEN** the server returns HTTP 200 status code with all external IDs associated with the entity

### Requirement: POST /entities/{id}/external-ids adds external ID
The system SHALL return HTTP 201 status code with the created external ID record when a client makes a POST request to /entities/{id}/external-ids endpoint.

#### Scenario: Add external ID to entity
- **WHEN** a client makes a POST request to /entities/{id}/external-ids endpoint with external ID data
- **THEN** the server returns HTTP 201 status code with the created external ID record
