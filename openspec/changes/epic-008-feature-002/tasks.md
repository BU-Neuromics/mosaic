## 1. Core Search Implementation

- [x] 1.1 Add search method signature to EntityStore interface (epic-004-feature-001)
- [x] 1.2 Define ScoredMatch named tuple with entity_id, score, highlights fields
- [x] 1.3 Define SearchCapabilityError exception class
- [x] 1.4 Implement score normalization function (BM25 to 0.0-1.0)

## 2. SQLite FTS5 Query Implementation

- [x] 2.1 Implement FTS5 search query in SQLite adapter
- [x] 2.2 Handle BM25 ranking with FTS5 bm25() function
- [x] 2.3 Add field validation to check for search: fts in schema
- [x] 2.4 Implement SearchCapabilityError for non-FTS fields

## 3. Parameter Handling

- [x] 3.1 Implement min_score filtering logic
- [x] 3.2 Implement limit parameter with default of 100
- [x] 3.3 Add entity_type parameter validation

## 4. Testing

- [x] 4.1 Write unit tests for ScoredMatch normalization
- [x] 4.2 Write integration tests for search with FTS-indexed field
- [x] 4.3 Write tests for min_score filtering
- [x] 4.4 Write tests for limit parameter
- [x] 4.5 Write test for SearchCapabilityError on non-FTS field
