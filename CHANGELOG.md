# Changelog

## v0.4.0 — 2026-04-14

### Breaking Changes

- **`client.query()` return type changed from `list[dict]` to `PaginatedResult`.**
  Callers that iterate the return value directly (`for e in client.query(...)`) must update
  to iterate via `.items` (`for e in client.query(...).items`). The `PaginatedResult` object
  exposes `items: list[dict]`, `total: int`, `limit: int`, and `offset: int`. `total`
  reflects the count of all matching entities before `limit`/`offset` are applied — callers
  can use this to implement pagination UI without a separate count query.

- **Hippo DSL removed.** All schema authoring is now exclusively LinkML. The `compile-schema`
  CLI command, `HippoDSLLoader`, `schema_compiler.py`, and all DSL-related APIs have been
  deleted. Use `EntityYAMLLoader` for structured entity YAML ingestion. The entity YAML format
  (`entities: [{type, data, external_id}]`) is unchanged — only the class/function names changed:
  `HippoDSLLoader` → `EntityYAMLLoader`, `ingest_dsl_file` → `ingest_entity_file`,
  `IngestDSLError` → `IngestError`, `IngestDSLResult` → `IngestResult`.

### New Features

- **PostgreSQL storage adapter.** Hippo now supports PostgreSQL as a storage backend in
  addition to SQLite. Configure via `hippo.yaml` adapter settings.

- **v0.5 enhancements:** PUT endpoint for entity upsert, bulk operations API, OR filters
  in query expressions, and schema migration tooling.

- **`schema_references()` API + GA4GH DRS server.** Query schema-level relationship
  metadata and serve data objects via the GA4GH Data Repository Service standard.

- **Unified ingestion framework.** `EntityLoader` ABC with `ConfigurableLoader` base class
  and built-in loaders: `CSVLoader`, `JSONLoader`, `SQLLoader`, `EntityYAMLLoader`.
  `IngestPipeline` orchestrates fetch → transform → validate → write for any loader.

- **`client.supersede_entity(entity_id, replacement_id, reason=None, actor=None)`**
  Atomically marks an entity as superseded by a replacement:
  - Sets `is_available = false` on the source entity.
  - Sets `superseded_by = replacement_id` on the source entity (new system column).
  - Writes an `EntitySuperseded` provenance event on the source entity.
  - Writes a `superseded_by` relationship edge from source to replacement.
  - Writes an `EntityUpdated` provenance event on the replacement entity.
  All five writes are transactional — partial failure rolls back entirely.
  Raises `EntityAlreadySupersededError` if the source entity is already superseded.
  Raises `EntityNotFoundError` if either entity does not exist.

- **`EntityAlreadySupersededError`** — new exception class in `core/exceptions.py`.

- **`superseded_by` system field on all entities.**
  `client.get()` now returns `superseded_by` in the entity dict. `hippo migrate` adds this
  column to all entity tables via `ALTER TABLE ... ADD COLUMN superseded_by TEXT`.

- **`entity_provenance_summary` view created by `hippo migrate`.**
  Provides efficient batch derivation of `created_at` and `updated_at` for `client.query()`.

### Refactor

- **Decomposed `HippoClient` into domain facades** for better separation of concerns.
- **Removed Hippo DSL compiler and compile-schema CLI command.** Schemas are authored
  directly in LinkML — no intermediate compilation step.

### Behaviour Changes

- **`client.get()` and `client.query()` now return provenance-derived `created_at` and
  `updated_at`** (authoritative source per spec). Entity table columns are treated as a
  write-through cache; reads derive values from the provenance log.

- **`client.get()` now returns superseded entities** with `superseded_by` populated.

- **`client.history()` now works on superseded entities.**

### Bug Fixes

- Fix ingest idempotency — catch `EntityNotFoundError` explicitly in `_upsert_records`.
- Resolve CI test failures across Canon, Hippo, and Cappella test suites.

### Documentation

- Rewrite all schema examples to valid LinkML format.
- Remove legacy Hippo DSL references from all specs and docs.
- Consolidate `user-docs/` into `docs/` across all components.
- Add Schema Writer's Guide and auth integration spec (sec8).
- Spec Phase 1 REST API gaps in sec4 (v0.5 targets).

## v0.3.1 — 2026-03-25

### Bug Fixes

- **`client.get()` now raises `EntityNotFoundError` for deleted and superseded entities by default.**
  Previously, `get()` silently returned unavailable entities via a `read_any()` fallback, inconsistent
  with `query()` which already excludes them. Added `include_unavailable=False` parameter — set to `True`
  for audit/provenance queries that need to read deleted or superseded entities.

- **`client.update()` now raises `EntityNotFoundError` for nonexistent, deleted, or superseded entities.**
  Previously, `update()` on a nonexistent entity ID silently upserted (created a new entity), which
  was a data integrity bug. Now verifies the entity exists and is available before proceeding.

### Tests

- Added `tests/core/test_client_availability.py` — 16 unit tests covering availability filtering
  and update existence checks, developed via TDD (red → green → refactor).
- Platform-level integration test suite added at monorepo root (`tests/platform/`, `tests/contracts/`):
  937 total tests passing across all three tiers (unit, contract, platform).
