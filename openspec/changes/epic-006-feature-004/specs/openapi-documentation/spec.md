## ADDED Requirements

### Requirement: Swagger UI Endpoint
The system SHALL provide a Swagger UI interface at the `/docs` endpoint for interactive API documentation.

#### Scenario: GET request to docs endpoint
- **WHEN** a client makes a GET request to `/docs` endpoint
- **THEN** the server SHALL return HTTP 200 status code with content type `text/html`

#### Scenario: Swagger UI renders correctly
- **WHEN** a GET request is made to `/docs` endpoint
- **THEN** the response SHALL render the Swagger UI interface with all available API endpoints

### Requirement: OpenAPI JSON Schema Endpoint
The system SHALL provide an OpenAPI schema endpoint at `/openapi.json` that returns the raw OpenAPI specification in JSON format.

#### Scenario: GET request to openapi.json endpoint
- **WHEN** a client makes a GET request to `/openapi.json` endpoint
- **THEN** the server SHALL return HTTP 200 status code with content type `application/json`

#### Scenario: Valid OpenAPI schema returned
- **WHEN** a client makes a GET request to `/openapi.json` endpoint
- **THEN** the response SHALL contain a valid OpenAPI schema definition with paths, components, and info

### Requirement: Docstrings Appear in OpenAPI Spec
The system SHALL include operation information from docstrings in the generated OpenAPI specification.

#### Scenario: Endpoint with docstrings in spec
- **WHEN** an API endpoint has proper docstrings defined
- **THEN** the operation SHALL appear in the OpenAPI spec with correct path, method, parameters, and response definitions

### Requirement: All Routes Included in OpenAPI Spec
The system SHALL include all registered routes in the OpenAPI specification.

#### Scenario: All registered routes in spec
- **WHEN** the server starts up with enabled documentation generation
- **THEN** all registered routes SHALL be included in the OpenAPI specification

### Requirement: Swagger UI Grouping and Filtering
The system SHALL provide Swagger UI with proper grouping and filtering capabilities for API endpoints.

#### Scenario: Endpoints displayed with grouping
- **WHEN** a GET request is made to `/docs` endpoint
- **THEN** the UI SHALL display all available API endpoints with proper grouping (by path or tag)

#### Scenario: Endpoint filtering in Swagger UI
- **WHEN** a user views the Swagger UI interface
- **THEN** the UI SHALL provide filtering capabilities to search and filter endpoints