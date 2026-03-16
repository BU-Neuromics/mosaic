## ADDED Requirements

### Requirement: GET /search returns matching entities
The system SHALL return HTTP 200 status code with a JSON array of entity objects matching the search criteria when a client makes a GET request to the /search endpoint.

#### Scenario: Search with query parameter
- **WHEN** a client makes a GET request to /search endpoint with query parameter "q=sample"
- **THEN** the server returns HTTP 200 status code with entities matching the search query

### Requirement: GET /search supports pagination
The system SHALL return paginated results when a client makes a GET request to /search endpoint with limit and offset parameters.

#### Scenario: Paginated search results
- **WHEN** a client makes a GET request to /search endpoint with "limit=10" and "offset=0" parameters
- **THEN** the server returns HTTP 200 with at most 10 entities starting from offset 0
