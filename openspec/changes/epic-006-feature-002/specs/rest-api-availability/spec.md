## ADDED Requirements

### Requirement: GET /entities/{id}/availability returns availability status
The system SHALL return HTTP 200 status code with the entity's availability status when a client makes a GET request to /entities/{id}/availability endpoint.

#### Scenario: Retrieve availability status
- **WHEN** a client makes a GET request to /entities/{id}/availability endpoint
- **THEN** the server returns HTTP 200 status code with the availability status (active, archived, deleted, etc.)

### Requirement: POST /entities/{id}/availability updates availability status
The system SHALL return HTTP 200 status code with the updated entity when a client makes a POST request to /entities/{id}/availability endpoint with a new availability status.

#### Scenario: Update availability status
- **WHEN** a client makes a POST request to /entities/{id}/availability endpoint with new status
- **THEN** the server returns HTTP 200 status code with the updated entity showing the new availability status
