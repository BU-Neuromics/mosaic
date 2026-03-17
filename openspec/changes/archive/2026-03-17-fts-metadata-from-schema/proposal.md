# FTS Metadata Derived from Schema in HippoClient

## Goal

`HippoClient` currently relies on `_fts_table_metadata` being set externally
(e.g. by a test harness or calling code) to know which entity fields are
FTS-indexed.  This is a leaky abstraction: the storage-level detail of which
virtual tables back which fields is being pushed up into the caller.

The fix is to derive FTS table metadata automatically from the `SchemaConfig`
objects that `HippoClient` already accepts via its `schemas` constructor
parameter.

## Problem

When `HippoClient` is constructed with `schemas=` containing `FieldDefinition`
entries that carry `search: fts5`, it does **not** automatically build the FTS
table routing metadata it needs.  Instead, callers must manually set:

```python
client._fts_table_metadata = {
    "Sample": [FTSTableMetadata(...)]
}
```

This breaks encapsulation in two ways:

1. **Wrong layer** — the client is the right place to own the schema→FTS
   mapping, not the caller.
2. **Adapter leak** — `FTSTableMetadata` is a storage-layer type.  Callers
   and tests should not need to construct it.

## Proposed Change

In `HippoClient.__init__`, after storing `self._schemas`, call a private
method `_build_fts_metadata()` that iterates over `self._schemas`, finds all
fields with `search: fts5` (or any FTS variant), and constructs the
`_fts_table_metadata` dict using `FTSTableMetadata.from_field()`.

The client's write path (`_sync_entity_to_fts`) and search path already use
`_fts_table_metadata` correctly — only the initialisation step is missing.

## Acceptance Criteria

- Given a `HippoClient` constructed with `schemas={"Sample": schema_config}`
  where `schema_config` has a field `notes` with `search="fts5"`, when
  `client._get_fts_tables_for_entity_type("Sample")` is called, then it
  returns a non-empty list of `FTSTableMetadata` without the caller having
  set `_fts_table_metadata` directly.

- Given the above client, when `client.create("Sample", {..., "notes": "..."})` 
  is called, then the FTS virtual table is populated automatically.

- Given the above client, when `client.search("Sample", "query")` is called,
  then results are returned based on the FTS index without any manual wiring.

- Given a `HippoClient` constructed **without** `schemas=`, then
  `_fts_table_metadata` is an empty dict and FTS search returns `[]` (no
  regression on existing behaviour).

- Given a schema field with `search=None` or no `search` key, then that field
  does not appear in `_fts_table_metadata` (non-FTS fields are not indexed).

## Files Affected

- `src/hippo/core/client.py` — add `_build_fts_metadata()`, call from
  `__init__`
- `tests/integration/test_e2e.py` — update `_make_client()` and FTS tests to
  pass `schemas=` instead of setting `_fts_table_metadata` directly
- `tests/core/test_client.py` — add unit tests for `_build_fts_metadata()`

## Constraints

- No changes to the `SQLiteAdapter` or `FTSTableMetadata` classes.
- `_fts_table_metadata` remains the internal backing store; `_build_fts_metadata()`
  is the only new public-ish surface.
- The `schemas=` parameter type stays `dict[str, SchemaConfig]`.
- Backwards compatible: clients without `schemas=` continue to work unchanged.
