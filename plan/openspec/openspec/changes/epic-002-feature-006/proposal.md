# SQLite Immutability Triggers

## Goal
SQLite Immutability Triggers: Implement database-level immutable triggers for provenance records to ensure data integrity.

## Acceptance Criteria
- Given a provenance record exists with specific data, when an UPDATE operation attempts to modify the record's primary key, then the database rejects the modification with a constraint violation error
- Given a provenance record exists with specific data, when an UPDATE operation attempts to modify the record's timestamp field, then the database rejects the modification with a constraint violation error
- Given triggers are installed for provenance table, when a COMMIT occurs on a transaction that modifies provenance records, then all affected provenance events remain unchanged and immutable during the transaction scope
- Given data is stored in the provenance table, when a DELETE operation attempts to remove a provenance record, then the database rejects the deletion with a constraint violation error
- Given a provenance record exists, when an UPDATE operation attempts to modify any protected field including metadata or content, then the database raises an integrity constraint violation error

## Constraints
- Complexity: high
