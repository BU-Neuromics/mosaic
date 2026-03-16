# Design: FTS Metadata Derived from Schema in HippoClient

## Approach

Single targeted change in `HippoClient.__init__`: after `self._schemas` is
stored, call `_build_fts_metadata()` to populate `self._fts_table_metadata`.

```python
def __init__(self, ..., schemas=None):
    ...
    self._schemas = schemas
    self._fts_table_metadata: dict[str, list[FTSTableMetadata]] = {}
    self._build_fts_metadata()  # <-- new
    ...

def _build_fts_metadata(self) -> None:
    """Populate _fts_table_metadata from self._schemas."""
    if not self._schemas:
        return
    for entity_type, schema in self._schemas.items():
        fts_tables = []
        for field in schema.fields:
            if field.search and "fts" in field.search.lower():
                meta = FTSTableMetadata.from_field(field, entity_type=entity_type)
                fts_tables.append(meta)
        if fts_tables:
            self._fts_table_metadata[entity_type] = fts_tables
```

## Key Decisions

- **No new public API** — `_build_fts_metadata` is private. The `schemas=`
  parameter is the only user-facing surface (already exists).
- **`FTSTableMetadata.from_field()` is the canonical factory** — already used
  in the migration planner; reusing it keeps the table-name convention
  (`fts_{entity_type}_{field_name}`) consistent.
- **`_fts_table_metadata` initialised to `{}`** — replaces the current
  `hasattr` guard in `_get_fts_tables_for_entity_type`.
- **No changes to `SQLiteAdapter`** — the adapter's
  `get_fts_tables_for_entity_type()` remains for introspection/migration use
  only.

## Test Impact

`tests/integration/test_e2e.py` `_make_client()` helper currently:
1. Sets `client._fts_table_metadata` directly
2. Manually creates the FTS virtual table via `sqlite3`

After this change, step 1 goes away — pass `schemas=` instead. Step 2
(creating the FTS virtual table) remains necessary in tests because
`SQLiteAdapter.__init__` doesn't auto-create FTS tables from schema (that's
`hippo migrate`'s job).

The integration test fixture becomes:

```python
def _make_client(tmp_hippo, *, validation=False, fts=False):
    ...
    schemas = _parse_schema(tmp_hippo / "schema.yaml")  # returns dict[str, SchemaConfig]
    client = HippoClient(storage=storage, pipeline=pipeline, schemas=schemas)
    if fts:
        # still need to create the virtual table manually in tests
        _create_fts_tables(db_path, schemas)
    return client
```

## Risk

Low. The write path (`_sync_entity_to_fts`) and search path already consume
`_fts_table_metadata` correctly — only the population step is missing. The
change is additive and backwards compatible.
