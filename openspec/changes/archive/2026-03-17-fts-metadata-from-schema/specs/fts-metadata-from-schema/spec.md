# Spec: FTS Metadata Derived from Schema

## Requirements

**REQ-1:** `HippoClient.__init__` MUST call `_build_fts_metadata()` after
storing `self._schemas`.

**REQ-2:** `_build_fts_metadata()` MUST iterate all schemas and collect fields
where `field.search` is non-None and contains `"fts"` (case-insensitive).

**REQ-3:** For each matching field, `_build_fts_metadata()` MUST call
`FTSTableMetadata.from_field(field, entity_type=entity_type)` and append the
result to `self._fts_table_metadata[entity_type]`.

**REQ-4:** `self._fts_table_metadata` MUST be initialised to `{}` in
`__init__` (replacing the `hasattr` guard in `_get_fts_tables_for_entity_type`).

**REQ-5:** When `schemas=None` (default), `_build_fts_metadata()` MUST be a
no-op, leaving `_fts_table_metadata` as `{}`.

**REQ-6:** `tests/integration/test_e2e.py` `_make_client()` MUST be updated to
pass `schemas=` instead of setting `_fts_table_metadata` directly.

**REQ-7:** New unit tests in `tests/core/test_client.py` MUST cover:
- client with no schemas has empty `_fts_table_metadata`
- client with schema containing one FTS field has one entry
- client with schema containing no FTS fields has empty `_fts_table_metadata`
- client with multiple entity types populates all of them

## Scenarios

**Scenario A — schema-driven FTS wiring:**
Given a `SchemaConfig` for `Sample` with `notes` field (`search="fts5"`),
when `HippoClient(schemas={"Sample": schema})` is constructed,
then `client._get_fts_tables_for_entity_type("Sample")` returns
`[FTSTableMetadata(table_name="fts_sample_notes", ...)]`.

**Scenario B — no schemas, no FTS:**
Given `HippoClient()` constructed without `schemas=`,
when `client._get_fts_tables_for_entity_type("Sample")` is called,
then `[]` is returned.

**Scenario C — non-FTS fields ignored:**
Given a `SchemaConfig` with fields `name` (no search) and `notes` (`search="fts5"`),
when the client is constructed,
then only `notes` appears in `_fts_table_metadata`.

**Scenario D — integration test uses schemas, not internals:**
Given `_make_client(tmp_hippo, fts=True)` in `test_e2e.py`,
when the client is constructed,
then `_fts_table_metadata` is populated from `schemas=`, not set directly.
