## 1. Core Infrastructure

- [x] 1.1 Set up SQLite storage backend in hippo/core/
- [x] 1.2 Implement entity table schema with id, is_available fields
- [x] 1.3 Add version tracking to entity model
- [ ] 1.4 Create schema validation utilities using LinkML

## 2. Put Operation

- [x] 2.1 Implement put method on HippoClient
- [x] 2.2 Add entity ID generation (UUID)
- [x] 2.3 Implement version increment logic for updates
- [x] 2.4 Add schema validation before put
- [x] 2.5 Handle null/empty data validation

## 3. Get Operation

- [x] 3.1 Implement get method on HippoClient
- [x] 3.2 Add entity retrieval by ID
- [x] 3.3 Include metadata (timestamps, version, creator) in response
- [x] 3.4 Handle non-existent entity error

## 4. Query Operation

- [x] 4.1 Implement query method on HippoClient
- [x] 4.2 Add filter parsing for query criteria
- [x] 4.3 Implement date range filtering
- [x] 4.4 Add sorting by creation timestamp (ascending)
- [x] 4.5 Return empty list for no matches

## 5. Testing

- [x] 5.1 Write unit tests for put operation
- [x] 5.2 Write unit tests for get operation
- [x] 5.3 Write unit tests for query operation
- [x] 5.4 Test error cases (invalid schema, non-existent entity)
