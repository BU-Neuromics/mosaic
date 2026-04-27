# Changelog

## v0.5.0 — 2026-04-27

### Breaking Changes

- **`created_at` and `updated_at` dropped from entity tables (PTS-69).**
  These columns no longer exist in the storage layer. Both fields are now computed
  exclusively from the provenance log at read time and returned by `client.get()` and
  `client.query()`. Run `hippo migrate` to drop the legacy columns from an existing
  database; no data loss occurs because the provenance log is the authoritative source.

- **`ValidationFailed` raised on write (PTS-70).**
  Entities that fail schema validation now raise `ValidationFailed` at write time
  (previously, failures were silently logged). Callers that write entities without catching
  this exception will see it surface. This is intentional: silent validation bypass was a
  data-integrity hazard.

### New Features

- **`hippo.models.<namespace>` direct-import surface (PTS-71).**
  Pydantic model classes generated from a namespace's LinkML schema are now importable as
  `from hippo.models.<namespace> import <ClassName>`. The namespace module is generated
  lazily on first access and cached.

- **Pydantic typed-client surface.**
  `HippoClient` now exposes namespace-aware typed accessors backed by generated Pydantic
  models. `client.<namespace>.get(id)` returns a typed instance; `client.<namespace>.query()`
  returns `PaginatedResult[<Model>]`. The untyped `client.get()` / `client.query()` paths
  remain unchanged.

- **Computed temporal fields.**
  `created_at` and `updated_at` are derived from the provenance log at read time via
  `entity_provenance_summary` (a view created by `hippo migrate`). The values are consistent
  with the provenance record rather than the entity table, which was the authoritative source
  all along.

- **Reference-loader shape (PTS-74).**
  Reference loaders now produce well-typed fragments with explicit merge semantics: each
  fragment declares its `entity_type`, and the loader merges overlapping fields according to
  the schema rather than by positional order. The `ReferenceLoader` ABC and
  `ConfigurableReferenceLoader` base class are the new extension points.

- **actor_id ContextVar sentinel (PTS-68).**
  Actor identity is now threaded through nested SDK calls automatically via a `ContextVar`.
  The `UUID4_SENTINEL` value is resolved to the caller's actual UUID at write time;
  callers no longer need to pass `actor=...` explicitly on every inner call.

- **LinkML-native SchemaRegistry.**
  `SchemaRegistry` loads and merges `hippo_core.yaml` (system-level schema: `id`,
  `is_available`, `superseded_by`, `actor_id`) and `hippo_ext.yaml` (annotation
  vocabulary: `hippo_unique`, `hippo_immutable`, `hippo_computed`) into a three-layer
  merge with user schemas. `SchemaRegistry.validate_hippo_annotations()` hard-fails on
  unknown `hippo_*` annotations.

- **Provenance migration: ProvenanceRecord model.**
  `ProvenanceStore` has been replaced by a `ProvenanceRecord` dataclass. A DDL
  verification helper ensures the provenance table schema is current before writes;
  a write-guard helper prevents in-flight provenance events from racing with schema
  migration.

- **Unified validation envelope + REST surface.**
  The validation result envelope (`ValidationEnvelope`) now unifies SDK-level and
  REST-level validation feedback. The FastAPI transport layer uses the same envelope
  for 422 responses.

### Bug Fixes

- **actor_id UUID sentinel drift (PTS-68).** Under nested calls, the sentinel UUID was
  occasionally propagated to storage instead of being resolved to the caller's identity.
  The ContextVar implementation fixes this deterministically.

- **Hard-fail on Pydantic generation failure.** A prior revision allowed silent pass-through
  when model generation failed (e.g. due to a malformed schema). This is now a hard error
  surfaced immediately at schema-load time.

### Documentation

- **`docs/reference_typed_client.md`** — user guide for the Pydantic typed-client surface (PTS-72).
- **Sec6 provenance spec revision (PTS-73)** — light-touch pass to align the provenance spec
  with the finalized `ProvenanceRecord` model and `entity_provenance_summary` view.

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
