## ADDED Requirements

### Requirement: App Factory Creates FastAPI Instance
The system SHALL provide a factory function that creates and returns a configured FastAPI instance with mounted routers and global error handlers.

#### Scenario: Factory creates app with routers
- **WHEN** the app factory function is called with a list of router definitions
- **THEN** it SHALL return a FastAPI instance with all routers successfully mounted

#### Scenario: Factory creates app without routers
- **WHEN** the app factory function is called without any router definitions (or empty list)
- **THEN** it SHALL return a FastAPI instance created successfully without any mounted routers

### Requirement: Global ValidationError Handler
The system SHALL catch Pydantic ValidationError exceptions and return a proper HTTP 422 response with error details.

#### Scenario: Endpoint raises ValidationError
- **WHEN** an endpoint raises a ValidationError during request processing
- **THEN** the response SHALL return HTTP 422 status code with error details in the JSON body

### Requirement: Global EntityNotFoundError Handler
The system SHALL catch EntityNotFoundError exceptions and return a proper HTTP 404 response with an error message.

#### Scenario: Endpoint raises EntityNotFoundError
- **WHEN** an endpoint raises EntityNotFoundError during request processing
- **THEN** the response SHALL return HTTP 404 status code with proper error message in the JSON body

### Requirement: Global Generic Exception Handler
The system SHALL catch all unhandled exceptions and return a proper HTTP 500 response with an error message.

#### Scenario: Endpoint raises generic Exception
- **WHEN** an endpoint raises a generic Exception during request processing
- **THEN** the response SHALL return HTTP 500 status code with proper error message in the JSON body

### Requirement: Consistent Error Response Format
The system SHALL return error responses in a consistent JSON format.

#### Scenario: Error response format
- **WHEN** any error handler returns a response
- **THEN** the response SHALL include an `error` field with the error type and a `detail` field with the error message
