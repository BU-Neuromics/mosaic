## ADDED Requirements

### Requirement: FTS5 table creation during migration
Given a schema with a field declared with search fts, when hippo migrate runs, then an FTS5 virtual table MUST be created for that field with the correct content table configuration.

#### Scenario: Create FTS5 table for new FTS field
- **WHEN** a schema defines an entity type with a field containing `search: fts`
- **AND** the `hippo migrate` command is executed
- **THEN** an FTS5 virtual table MUST be created with the appropriate column definition
- **AND** the table MUST be configured with external content mode referencing the source entity table

#### Scenario: FTS5 table schema matches entity field
- **WHEN** an entity type has multiple fields, one marked as `search: fts`
- **AND** migration runs
- **THEN** the FTS5 table column definition MUST match the source field's type and constraints

### Requirement: FTS5 index update on entity write
Given an entity is written via client.put(), when the write completes, then the FTS5 virtual table for all fts-indexed fields on that entity type MUST be updated in the same transaction.

#### Scenario: New entity creates FTS entry
- **WHEN** a new entity is created with data in an FTS-indexed field
- **AND** client.put() is called
- **THEN** an entry MUST be inserted into the corresponding FTS5 virtual table
- **AND** this MUST occur in the same database transaction as the entity write

#### Scenario: Existing entity update modifies FTS content
- **WHEN** an existing entity's FTS-indexed field is updated
- **AND** client.put() is called
- **THEN** the FTS5 virtual table entry MUST be updated to reflect the new content
- **AND** this MUST occur in the same transaction as the entity update

### Requirement: FTS5 content removal on availability false
Given an entity's availability is set to false, when the write completes, then the FTS5 content for that entity MUST be removed from the virtual table.

#### Scenario: Entity availability set to false removes FTS entry
- **WHEN** an entity's `is_available` field is set to `false`
- **AND** client.put() is called
- **THEN** the corresponding entry MUST be removed from the FTS5 virtual table
- **AND** the main entity record MUST remain in the entity table

### Requirement: FTS5 table creation for new field on existing entity type
Given a schema migration adds a new fts field to an existing entity type, when hippo migrate runs, then a new FTS5 virtual table MUST be created and backfilled with existing entity data.

#### Scenario: New FTS field migration backfills existing data
- **WHEN** a schema migration adds a new field with `search: fts` to an existing entity type
- **AND** `hippo migrate` is executed
- **THEN** a new FTS5 virtual table MUST be created
- **AND** all existing entities with non-null values in that field MUST be inserted into the FTS table

#### Scenario: Backfill handles large datasets
- **WHEN** an entity type has more than 10,000 existing entities with FTS-indexed fields
- **AND** migration runs
- **THEN** the backfill MUST process entities in batches to avoid memory exhaustion
- **AND** progress MUST be logged during backfill

### Requirement: Full-text search returns matching entities
Given an FTS5 virtual table exists for an entity type, when a new entity is created with data matching a search term, then the entity MUST be retrievable using full-text search queries on that field.

#### Scenario: Search finds newly created entity
- **WHEN** an entity is created with "important data" in an FTS-indexed field
- **AND** a full-text search query is executed for the term "important"
- **THEN** the entity MUST be returned in the search results

#### Scenario: Search finds entity by partial word
- **WHEN** an entity contains "analysis" in an FTS-indexed field
- **AND** a search query uses the prefix "anal*"
- **THEN** the entity MUST be returned in the search results

### Requirement: FTS5 update on entity text modification
Given an FTS5 virtual table exists for an entity type, when an entity's text content is updated, then the FTS table MUST be updated to reflect the new content within the same transaction.

#### Scenario: FTS entry updated atomically with entity
- **WHEN** an entity's FTS-indexed field value changes from "old content" to "new content"
- **AND** client.put() completes successfully
- **THEN** searching for "old content" MUST NOT return the entity
- **AND** searching for "new content" MUST return the entity

### Requirement: FTS5 entry removal on entity hard delete
Given an entity has been written and indexed in an FTS5 table, when the entity is deleted from the main storage, then the corresponding entry MUST be removed from the FTS5 virtual table.

#### Scenario: Entity deletion removes FTS entry
- **WHEN** an entity exists with an FTS-indexed field containing "searchable text"
- **AND** the entity is hard-deleted from the system
- **THEN** the FTS5 virtual table MUST NOT contain any entry for that entity
- **AND** subsequent searches MUST NOT return the deleted entity
