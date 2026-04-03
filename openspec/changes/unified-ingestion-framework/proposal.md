## Why

Hippo's ingestion logic is split between `IngestionPipeline` (hardcoded CSV/JSON/JSONL methods), `ReferenceLoader` ABC (reference data plugins), and a stubbed `hippo ingest` CLI that doesn't work. Cappella reimplemented nearly identical CSV/JSON/SQL adapter logic. This creates maintenance burden, divergent behavior, and forces plugin authors to learn different ABCs for reference loaders vs. operational adapters.

We unify all data loading into a single `EntityLoader` ABC hierarchy in Hippo core. Everything that loads data into Hippo — reference loaders, Cappella adapters, CLI ingest — subclasses this one ABC. Generic loaders (CSV, JSON, SQL, Entity YAML) are bundled in Hippo core with config-driven field and vocabulary mapping.

## What Changes

- **New** `hippo.core.loaders` package — `EntityLoader` ABC, `ConfigurableLoader`, `IngestPipeline`
- **New** `CSVLoader`, `JSONLoader`, `SQLLoader`, `EntityYAMLLoader` — generic built-in loaders
- **New** `hippo ingest` CLI — rewired to use loader framework (file + config, no triggers)
- **Modified** `pyproject.toml` — `hippo[loaders-sql]`, `hippo[loaders-json]` extras
- **BREAKING** Deprecates `hippo.core.ingestion.IngestionPipeline` (keep utility functions `extract_fts_content`, `flatten_dict`)
- **BREAKING** Removes `hippo.core.data_sources` (stub config system)

## Capabilities

### New Capabilities
- `entity-loader-abc` — EntityLoader + ConfigurableLoader ABCs with field_map/vocabulary_map
- `csv-loader` — CSVLoader for tabular data (file, HTTP, bytes)
- `json-loader` — JSONLoader for JSON arrays/files (optional JSONPath via extras)
- `sql-loader` — SQLLoader for SQL databases (extras: hippo[loaders-sql])
- `entity-yaml-loader` — EntityYAMLLoader for structured entity YAML
- `ingest-pipeline` — IngestPipeline: fetch → transform → validate → upsert loop with idempotency
- `ingest-cli` — Rewired `hippo ingest` command

### Modified Capabilities
- (none — this is new infrastructure replacing stubs)

## Impact

- **Code:** New `hippo/src/hippo/core/loaders/` package (7 modules); modified CLI; deprecated `ingestion.py`
- **Dependencies:** SQLAlchemy and jsonpath-ng as optional extras only
- **Tests:** New `hippo/tests/core/test_loaders.py`; existing `test_ingest.py` CLI tests updated
- **Breaking:** `IngestionPipeline` import path changes; old `data_sources.py` removed
- **Cross-component:** Cappella will subclass `EntityLoader` in a linked change
