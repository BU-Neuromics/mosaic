## ADDED Requirements

### Requirement: POST /ingest creates new entity
The system SHALL return HTTP 201 status code with the created entity object including all input fields plus generated timestamp and id when a client makes a POST request to /ingest endpoint with valid JSON payload containing entity data.

#### Scenario: Successful entity creation
- **WHEN** a client makes a POST request to /ingest endpoint with valid JSON payload containing entity data
- **THEN** the server returns HTTP 201 status code with the created entity object including all input fields plus generated timestamp and id

### Requirement: POST /ingest validates required fields
The system SHALL return HTTP 422 status code with validation error message indicating which fields are missing when a client makes a POST request to /ingest endpoint with missing required fields in the JSON payload.

#### Scenario: Missing required fields
- **WHEN** a client makes a POST request to /ingest endpoint with missing required fields in the JSON payload
- **THEN** the server returns HTTP 422 status code with validation error message indicating which fields are missing

### Requirement: POST /ingest handles malformed JSON
The system SHALL return HTTP 400 status code with error message "Invalid JSON format" when a client makes a POST request to /ingest endpoint with malformed JSON in the request body.

#### Scenario: Malformed JSON body
- **WHEN** a client makes a POST request to /ingest endpoint with malformed JSON in the request body
- **THEN** the server returns HTTP 400 status code with error message "Invalid JSON format"
