# SQLite Provenance Table Implementation

## Goal
SQLite Provenance Table Implementation: Implement provenance tracking with dedicated table for immutable records at database level.

## Acceptance Criteria
- Given the EntityStore has implemented provenance, when an entity is created, then a provenance record with type "CREATE" is generated and stored in the provenance table with the entity's ID and current timestamp
- Given a record exists in the EntityStore, when a soft-delete operation occurs, then a provenance record with type "SOFT_DELETE" is created and stored in the provenance table maintaining the original data immutability
- Given transactions are committed in the EntityStore, when multiple write operations occur within the same transaction, then exactly one provenance event is created for each operation and all events are stored in the same transaction
- Given the provenance table is implemented, when a new entity is created, then the provenance record must include the entity ID, operation type, timestamp, and user context
- Given the provenance table is implemented, when an entity is soft-deleted, then the provenance record must contain the original entity data to ensure data immutability

## Constraints
- Complexity: medium
