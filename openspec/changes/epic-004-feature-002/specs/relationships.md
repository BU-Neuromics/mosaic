## ADDED Requirements

### Requirement: Entity relationship creation
The system SHALL allow creating typed relationships between two distinct entities with metadata.

#### Scenario: Successful relationship creation
- **WHEN** the relate operation is called with valid source entity ID, target entity ID, and relationship type
- **THEN** a new connection is created between the entities and relationship metadata including timestamp and creator is stored

#### Scenario: Multiple sequential relationships
- **WHEN** multiple relate operations are called sequentially with different relationship types
- **THEN** each connection is created independently and relationship metadata is properly maintained for each connection

#### Scenario: Invalid relationship type
- **WHEN** the relate operation is called with an invalid relationship type
- **THEN** an error is thrown indicating the unsupported relationship type and no connection is created

### Requirement: Entity relationship removal
The system SHALL allow removing specific relationships between entities while preserving other relationships.

#### Scenario: Successful relationship removal
- **WHEN** the unrelate operation is called with valid entity IDs and relationship type
- **THEN** the relationship is removed from the system and the action is recorded in history with timestamp and user

#### Scenario: Remove specific relationship type only
- **WHEN** two entities are connected through multiple relationship types and unrelate is called for one specific relationship type
- **THEN** only that relationship is removed while other relationships remain intact

### Requirement: Entity graph traversal
The system SHALL allow traversing entity relationships with configurable depth and filtering.

#### Scenario: Basic graph traversal
- **WHEN** the traverse operation is called with a valid starting entity ID and traversal parameters
- **THEN** all related entities are returned in a structured hierarchical format with proper relationship metadata at each level

#### Scenario: Traversal with depth limit
- **WHEN** the traverse operation is called with a depth limit parameter
- **THEN** traversal stops at specified depth and returns entities up to that level

#### Scenario: Traversal with filter parameters
- **WHEN** a traverse operation with filter parameters is called on entities with multiple connections
- **THEN** only entities matching the filter criteria are returned in the hierarchy structure

#### Scenario: Non-existent start entity
- **WHEN** the traverse operation is called with a non-existent starting entity ID
- **THEN** an error is returned indicating the entity does not exist and traversal is aborted

### Requirement: Relationship authorization
The system SHALL enforce authorization checks on relationship operations.

#### Scenario: Unauthorized relationship creation
- **WHEN** the relate operation is called without proper authentication token
- **THEN** an authorization error is thrown and no relationship is created
