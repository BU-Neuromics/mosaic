## ADDED Requirements

### Requirement: X-Hippo-Actor header extraction
The PassThroughAuthMiddleware SHALL extract the actor identifier from the X-Hippo-Actor header and attach it to the request context when the header is in the valid format "actor:<identifier>".

#### Scenario: Valid X-Hippo-Actor header present
- **WHEN** a request is received with a valid X-Hippo-Actor header containing "actor:<identifier>" where identifier is non-empty
- **THEN** the middleware SHALL extract the identifier and pass it as the actor identifier in the request context

#### Scenario: No X-Hippo-Actor header present
- **WHEN** a request is received without an X-Hippo-Actor header
- **THEN** the middleware SHALL continue processing with an empty actor identifier in the request context

#### Scenario: Invalid X-Hippo-Actor header format (not starting with "actor:")
- **WHEN** a request is received with an X-Hippo-Actor header that does not start with "actor:"
- **THEN** the middleware SHALL raise a 401 authentication error with message "Invalid X-Hippo-Actor header format"

#### Scenario: Empty actor identifier in X-Hippo-Actor header
- **WHEN** a request is received with X-Hippo-Actor header "actor:" (empty identifier after "actor:")
- **THEN** the middleware SHALL raise a 401 authentication error with message "Empty actor identifier in X-Hippo-Actor header"

#### Scenario: Multiple X-Hippo-Actor headers present
- **WHEN** a request is received with multiple X-Hippo-Actor headers
- **THEN** the middleware SHALL use the first header value and process it according to the valid format rules

### Requirement: AuthMiddleware Abstract Base Class
The system SHALL provide an AuthMiddleware Abstract Base Class that defines the interface for authentication middleware implementations.

#### Scenario: Custom middleware implementation
- **WHEN** a developer creates a subclass of AuthMiddleware
- **THEN** the subclass MUST implement the abstract methods to provide custom authentication logic
