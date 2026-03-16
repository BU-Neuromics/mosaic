## ADDED Requirements

### Requirement: GET /entities returns entity list
The system SHALL return HTTP 200 status code with a JSON array of entity objects when a client makes a GET request to the /entities endpoint with valid authentication headers.

#### Scenario: Successful entity list retrieval
- **WHEN** a client makes a GET request to /entities endpoint with valid authentication headers
- **THEN** the server returns HTTP 200 status code with a JSON array containing entity objects with id, name, type, and metadata fields

### Requirement: GET /entities supports filtering
The system SHALL return HTTP 200 status code with filtered entity results when a client makes a GET request to /entities endpoint with query parameters for filtering.

#### Scenario: Filter by entity type
- **WHEN** a client makes a GET request to /entities endpoint with query parameter "type=Sample"
- **THEN** the server returns HTTP 200 status code with only entities of type "Sample"

#### Scenario: Filter by entity name
- **WHEN** a client makes a GET request to /entities endpoint with query parameter "name=sample-001"
- **THEN** the server returns HTTP 200 status code with entities matching the name filter

### Requirement: Unauthenticated request returns 401
The system SHALL return HTTP 401 status code with error message "Unauthorized access" when a client makes a GET request to /entities endpoint without authentication headers.

#### Scenario: Request without authentication
- **WHEN** a client makes a GET request to /entities endpoint without authentication headers
- **THEN** the server returns HTTP 401 status code with error message "Unauthorized access"

### Requirement: GET /entities/{id} returns single entity
The system SHALL return HTTP 200 status code with a single entity object when a client makes a GET request to /entities/{id} endpoint.

#### Scenario: Successful single entity retrieval
- **WHEN** a client makes a GET request to /entities/{id} endpoint with valid authentication
- **THEN** the server returns HTTP 200 status code with the entity object

#### Scenario: Entity not found
- **WHEN** a client makes a GET request to /entities/{id} endpoint for a non-existent entity
- **THEN** the server returns HTTP 404 status code with error message "Entity not found"
