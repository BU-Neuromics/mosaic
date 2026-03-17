## ADDED Requirements

### Requirement: Put Entity
The system SHALL allow creating or updating an entity with proper versioning and unique identifier.

#### Scenario: Create new entity with valid schema
- **WHEN** a researcher calls put operation with a valid entity schema
- **THEN** the entity is created in the system with a unique identifier and version 1

#### Scenario: Update existing entity
- **WHEN** a researcher calls put operation with an existing entity ID but different data
- **THEN** the entity is updated with new data and version number incremented by one

#### Scenario: Put with null or empty data
- **WHEN** a researcher calls put operation with null or empty data
- **THEN** the system throws a bad request error with validation message

#### Scenario: Put with invalid schema
- **WHEN** a researcher calls put operation with an entity that has invalid schema
- **THEN** the system throws a validation error with specific error code and message

### Requirement: Get Entity
The system SHALL allow retrieving an entity by its ID with all metadata.

#### Scenario: Get existing entity
- **WHEN** a researcher calls get operation with an existing entity ID
- **THEN** the entity data is returned with all metadata including timestamps, version number, and creator information

#### Scenario: Get non-existent entity
- **WHEN** a researcher calls get operation with a non-existent entity ID
- **THEN** the system throws a resource not found error with specific error code

#### Scenario: Consistent get calls
- **WHEN** a researcher makes multiple get calls for the same entity
- **THEN** the same data and metadata are consistently returned across all calls

### Requirement: Query Entities
The system SHALL allow querying entities with specific filter criteria.

#### Scenario: Query with matching criteria
- **WHEN** a researcher calls query operation with specific filter criteria
- **THEN** entities are filtered and returned based on provided criteria matching the expected data types and values

#### Scenario: Query with no matches
- **WHEN** a researcher calls query operation with criteria that match no entities
- **THEN** an empty list is returned with success status code

#### Scenario: Query with date range filter
- **WHEN** a researcher calls query operation with date range filter
- **THEN** entities are returned sorted by creation timestamp in ascending order

#### Scenario: Query with multiple attributes
- **WHEN** a researcher calls query operation with multiple different attributes
- **THEN** entities are filtered and returned based on all provided criteria
