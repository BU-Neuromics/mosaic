# Authentication Middleware Implementation

## Goal
Authentication Middleware Implementation: Implements AuthMiddleware ABC and pass-through stub that extracts X-Hippo-Actor header for request identification.

## Acceptance Criteria
- Given a valid X-Hippo-Actor header with format "actor:<identifier>" is present, when the request is processed, then it extracts the identifier and passes it as actor identifier in the request context
- Given no X-Hippo-Actor header is present, when the request is processed, then it continues with empty actor identifier in the request context
- Given an invalid X-Hippo-Actor header format (not starting with "actor:"), when the request is processed, then it raises a 401 authentication error with message "Invalid X-Hippo-Actor header format"
- Given an X-Hippo-Actor header with empty identifier after "actor:", when the request is processed, then it raises a 401 authentication error with message "Empty actor identifier in X-Hippo-Actor header"
- Given multiple X-Hippo-Actor headers are present, when the request is processed, then it uses the first header value and processes it according to the valid format rules

## Constraints
- Complexity: medium
