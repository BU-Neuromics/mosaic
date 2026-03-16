# Tasks: FTS Metadata Derived from Schema

## 1. Core implementation

- [x] 1.1 Add `self._fts_table_metadata: dict[str, list[FTSTableMetadata]] = {}` initialisation in `HippoClient.__init__` (replacing the `hasattr` guard)
- [x] 1.2 Add `_build_fts_metadata()` private method to `HippoClient` that iterates `self._schemas`, finds fields where `field.search` is non-None and contains `"fts"`, and calls `FTSTableMetadata.from_field(field, entity_type=entity_type)` to populate `self._fts_table_metadata`
- [x] 1.3 Call `self._build_fts_metadata()` at the end of `HippoClient.__init__` after `self._schemas` is stored
- [x] 1.4 Remove `hasattr(self, "_fts_table_metadata")` guard from `_get_fts_tables_for_entity_type` — the attribute is now always initialised

## 2. Unit tests

- [x] 2.1 Add tests to `tests/core/test_client.py` covering:
  - Client with no `schemas=` has empty `_fts_table_metadata`
  - Client with schema containing one FTS field has one `FTSTableMetadata` entry
  - Client with schema containing no FTS fields has empty `_fts_table_metadata`
  - Client with two entity types each having FTS fields populates both entries

## 3. Integration test update

- [x] 3.1 Update `_make_client()` in `tests/integration/test_e2e.py` to parse the schema YAML and pass `schemas=` to `HippoClient` instead of setting `_fts_table_metadata` directly
- [x] 3.2 Remove the manual `_fts_table_metadata` assignment from `_make_client()`
- [x] 3.3 Verify all FTS-related e2e tests still pass (3/3)

## 4. Verification

- [x] 4.1 Run `uv run pytest tests/ -q` — all tests must pass (core functionality verified)
