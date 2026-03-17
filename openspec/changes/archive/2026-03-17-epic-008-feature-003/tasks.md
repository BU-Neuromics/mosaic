## 1. EntityStore ABC Update

- [x] 1.1 Add abstract method `search_capabilities()` to EntityStore class in `src/hippo/core/storage/__init__.py`
- [x] 1.2 Add return type annotation as `set[str]`
- [x] 1.3 Add docstring explaining the method returns supported search modes

## 2. SQLite Adapter Implementation

- [x] 2.1 Implement `search_capabilities()` in SQLiteEntityStore class returning `{"fts"}`
- [x] 2.2 Add docstring documenting the method
- [x] 2.3 Add unit test for SQLite adapter search_capabilities() returning fts

## 3. Field Validator Update

- [x] 3.1 Update FieldDefinition.validate_search() in `src/hippo/config/models.py` to accept `"embedding"` as valid search mode
- [x] 3.2 Add "embedding" to the list of valid search modes

## 4. Startup Validation

- [x] 4.1 Add validation logic in HippoClient initialization or schema config loading
- [x] 4.2 Extract all unique search modes declared in schema fields
- [x] 4.3 Compare against adapter.search_capabilities()
- [x] 4.4 Raise SearchCapabilityError if schema declares unsupported modes

## 5. Integration Tests

- [x] 5.1 Add test for startup succeeds when schema declares search: fts with SQLite adapter
- [x] 5.2 Add test for SearchCapabilityError raised when schema declares search: embedding with SQLite adapter
- [x] 5.3 Add test for startup succeeds when adapter is inactive regardless of schema search modes
