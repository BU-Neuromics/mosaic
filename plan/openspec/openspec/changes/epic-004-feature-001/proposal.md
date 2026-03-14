# HippoClient Core CRUD Operations

## Goal
HippoClient Core CRUD Operations: Implementation of basic entity operations including put, get, query, and state management for the HippoClient.

## Acceptance Criteria
- Given a researcher has defined an entity with valid schema, when they call put operation with that entity, then the entity is created or updated in the system with proper versioning and a unique identifier
- Given an existing entity exists with valid data, when they call get operation by entity ID, then the entity data is returned with all metadata including timestamps, version number, and creator information
- Given multiple entities exist with different attributes, when they call query operation with specific filter criteria, then entities are filtered and returned based on provided criteria matching the expected data types and values
- Given an existing entity exists with valid data, when they call put operation with same ID but different data, then the entity is updated with new data and version number incremented by one
- Given a researcher has defined an entity with invalid schema, when they call put operation with that entity, then the system throws a validation error with specific error code and message
- Given no entities match query criteria, when they call query operation, then an empty list is returned with success status code
- Given multiple entities exist with varying timestamps, when they call query operation with date range filter, then entities are returned sorted by creation timestamp in ascending order
- Given an existing entity exists, when they make multiple get calls, then the same data and metadata are consistently returned across all calls
- Given a researcher tries to access an entity that does not exist, when they call get operation with non-existent ID, then the system throws a resource not found error with specific error code
- Given a researcher has defined an entity with valid schema, when they call put operation with null or empty data, then the system throws a bad request error with validation message

## Constraints
- Complexity: low
