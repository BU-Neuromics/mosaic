## ADDED Requirements

### Requirement: Client can register an external ID for an entity
The HippoClient SHALL support registering an external identifier for an existing entity, allowing external systems to reference the entity by their own ID scheme.

#### Scenario: Register first external ID for entity
- **WHEN** an entity exists with no external identifiers
- **AND** the client calls `register_external_id(entity_id, "EXT-001")`
- **THEN** the external identifier "EXT-001" is associated with the entity
- **AND** the client can retrieve the entity using `get_by_external_id("EXT-001")`

#### Scenario: Register additional external ID for entity
- **WHEN** an entity has an existing external ID "EXT-001"
- **AND** the client calls `register_external_id(entity_id, "EXT-002")`
- **THEN** both external IDs "EXT-001" and "EXT-002" are associated with the entity
- **AND** the client can retrieve the entity using either external ID

#### Scenario: Register external ID that already exists for another entity fails
- **WHEN** entity A exists with external ID "EXT-001"
- **AND** entity B exists with no external IDs
- **AND** the client calls `register_external_id(entity_b_id, "EXT-001")`
- **THEN** registration fails with an appropriate error code or validation message

### Requirement: Client can supersede an entity's external ID
The HippoClient SHALL support replacing an entity's external ID with a new one while preserving the historical association in the provenance log.

#### Scenario: Supersede external ID successfully
- **WHEN** an entity has an existing external ID "EXT-001"
- **AND** the client calls `supersede(entity_id, "EXT-001", "EXT-002")`
- **THEN** the old external ID "EXT-001" is marked as superseded
- **AND** the new external ID "EXT-002" is associated with the entity
- **AND** the client can retrieve the entity using `get_by_external_id("EXT-002")`

#### Scenario: Sequential supersedes replace previous ID
- **WHEN** an entity has an existing external ID "EXT-001"
- **AND** the client calls `supersede(entity_id, "EXT-001", "EXT-002")`
- **AND** the client calls `supersede(entity_id, "EXT-002", "EXT-003")`
- **THEN** "EXT-001" is marked as superseded
- **AND** "EXT-002" is marked as superseded
- **AND** "EXT-003" is the current external ID
- **AND** the client can retrieve the entity using `get_by_external_id("EXT-003")`

### Requirement: Client can retrieve an entity by external ID
The HippoClient SHALL support looking up an entity by its external identifier, returning the entity with the latest registration timestamp when multiple entities have used the same external ID over time.

#### Scenario: Get entity by external ID returns correct entity
- **WHEN** multiple entities exist with overlapping external IDs
- **AND** entity A was registered with "EXT-001" at time T1
- **AND** entity B was registered with "EXT-001" at time T2 (where T2 > T1)
- **AND** the client calls `get_by_external_id("EXT-001")`
- **THEN** entity B is returned (latest registration)

#### Scenario: Get entity by superseded ID returns NotFound
- **WHEN** an entity has only one external ID "EXT-001"
- **AND** "EXT-001" is superseded by "EXT-002"
- **AND** the client calls `get_by_external_id("EXT-001")`
- **THEN** a NotFound error or null response is returned

#### Scenario: Get entity by one of multiple external IDs
- **WHEN** an entity has external IDs "EXT-001" and "EXT-002"
- **AND** the client calls `get_by_external_id("EXT-001")`
- **THEN** the entity is returned
- **AND** the external ID "EXT-002" association remains intact

#### Scenario: Get entity by non-existent external ID returns NotFound
- **WHEN** no entity exists with external ID "NON-EXISTENT"
- **AND** the client calls `get_by_external_id("NON-EXISTENT")`
- **THEN** a NotFound error is returned

#### Scenario: Multiple entities with different external IDs can be retrieved independently
- **WHEN** entity A has external ID "EXT-A"
- **AND** entity B has external ID "EXT-B"
- **AND** the client calls `get_by_external_id("EXT-A")`
- **THEN** entity A is returned
- **AND** the client calls `get_by_external_id("EXT-B")`
- **AND** entity B is returned
