## 1. Schema and Configuration

- [x] 1.1 Extend schema config to support `search: fts` field option
- [x] 1.2 Add FTS field detection in SchemaConfig class
- [x] 1.3 Create FTS table metadata model (table name, columns, source entity mapping)

## 2. Storage Adapter Layer

- [x] 2.1 Add FTS5 virtual table creation method to SQLite storage adapter
- [x] 2.2 Implement FTS5 table schema generation from field metadata
- [x] 2.3 Add FTS5 content sync methods (insert, update, delete)
- [x] 2.4 Implement external content FTS5 configuration

## 3. Migration Pipeline

- [x] 3.1 Add FTS table detection to migration planner
- [x] 3.2 Implement FTS table creation during hippo migrate
- [x] 3.3 Add backfill logic for existing entities
- [x] 3.4 Implement batched backfill with progress tracking

## 4. Entity Write Integration

- [x] 4.1 Modify IngestionPipeline to detect FTS-indexed fields
- [x] 4.2 Add FTS index update to entity write transaction
- [x] 4.3 Handle availability=false as FTS DELETE operation
- [x] 4.4 Ensure atomicity between entity and FTS updates

## 5. Query Engine

- [x] 5.1 Add full-text search query method to QueryEngine
- [x] 5.2 Implement FTS query syntax generation from search parameters
- [x] 5.3 Add FTS result mapping back to entity queries

## 6. Testing

- [x] 6.1 Write unit tests for FTS table creation
- [x] 6.2 Write integration tests for entity write FTS sync
- [x] 6.3 Write tests for availability transition handling
- [x] 6.4 Write tests for migration backfill
- [x] 6.5 Add query engine FTS search tests
