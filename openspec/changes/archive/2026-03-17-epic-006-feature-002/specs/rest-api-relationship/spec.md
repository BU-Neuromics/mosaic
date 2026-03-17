## ADDED Requirements

### Requirement: GET /entities/{id}/relationships returns entity relationships
The system SHALL return HTTP 200 status code with a JSON array of relationship objects when a client makes a GET request to /entities/{id}/relationships endpoint.

#### Scenario: Retrieve entity relationships
- **WHEN** a client makes a GET request to /entities/{id}/relationships endpoint
- **THEN** the server returns HTTP 200 status code with all relationships associated with the entity

### Requirement: POST /entities/{id}/relationships creates relationship
The system SHALL return HTTP 201 status code with the created relationship when a client makes a POST request to /entities/{id}/relationships endpoint.

#### Scenario: Create new relationship
- **WHEN** a client makes a POST request to /entities/{id}/relationships endpoint with relationship data
- **THEN** the server returns HTTP 201 status code with the created relationship

### Requirement: DELETE /entities/{id}/relationships/{rel_id} removes relationship
The system SHALL return HTTP 204 status code when a client makes a DELETE request to /entities/{id}/relationships/{rel_id} endpoint.

#### Scenario: Delete relationship
- **WHEN** a client makes a DELETE request to /entities/{id}/relationships/{rel_id} endpoint
- **THEN** the server returns HTTP 204 status code and removes the relationship
