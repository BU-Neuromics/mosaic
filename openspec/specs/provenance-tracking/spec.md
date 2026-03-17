# provenance-tracking Specification

## Purpose
TBD - created by archiving change epic-002-feature-004. Update Purpose after archive.
## Requirements
### Requirement: Entity CREATE generates provenance record
Given the EntityStore has implemented provenance, when an entity is created, then a provenance record with type "CREATE" is generated and stored in the provenance table with the entity's ID and current timestamp.

#### Scenario: CREATE event on new entity
- **WHEN** a new entity is created in the EntityStore
- **THEN** a provenance record with operation_type "CREATE" MUST be generated
- **AND** the record MUST include the entity's ID
- **AND** the record MUST include the current timestamp

### Requirement: Soft-delete generates provenance record
Given a record exists in the EntityStore, when a soft-delete operation occurs, then a provenance record with type "SOFT_DELETE" is created and stored in the provenance table maintaining the original data immutability.

#### Scenario: SOFT_DELETE event preserves original data
- **WHEN** an entity is soft-deleted in the EntityStore
- **THEN** a provenance record with operation_type "SOFT_DELETE" MUST be generated
- **AND** the record MUST contain the original entity data
- **AND** the original data MUST remain immutable in the provenance record

### Requirement: Transaction-bound provenance events
Given transactions are committed in the EntityStore, when multiple write operations occur within the same transaction, then exactly one provenance event is created for each operation and all events are stored in the same transaction.

#### Scenario: Multiple operations in single transaction
- **WHEN** multiple write operations occur within the same database transaction
- **THEN** exactly one provenance record MUST be created for each operation
- **AND** all provenance records MUST be stored in the same transaction as the entity operations

### Requirement: Provenance record includes user context
Given the provenance table is implemented, when a new entity is created, then the provenance record MUST include the entity ID, operation type, timestamp, and user context.

#### Scenario: User context captured in provenance
- **WHEN** an entity operation is performed
- **THEN** the provenance record MUST include user context information

### Requirement: Original data preserved on soft-delete
Given the provenance table is implemented, when an entity is soft-deleted, then the provenance record MUST contain the original entity data to ensure data immutability.

#### Scenario: Original entity state preserved
- **WHEN** an entity is soft-deleted
- **THEN** the provenance record MUST contain the complete original entity data
- **AND** the data MUST be stored in a format that allows exact reconstruction

