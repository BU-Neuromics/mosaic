## 1. Core Implementation

- [ ] 1.1 Implement `_build_fts_metadata()` method in `HippoClient`
- [ ] 1.2 Update `HippoClient.__init__` to call `_build_fts_metadata()`
- [ ] 1.3 Initialize `_fts_table_metadata` to `{}` instead of using `hasattr` guard

## 2. Test Updates

- [ ] 2.1 Update integration test helper `_make_client()` in `tests/integration/test_e2e.py` to pass `schemas=` instead of setting `_fts_table_metadata` directly
- [ ] 2.2 Add unit tests for `_build_fts_metadata()` in `tests/core/test_client.py`