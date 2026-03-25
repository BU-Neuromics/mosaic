# Changelog

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

## Unreleased

### Breaking Changes

- **`client.query()` return type changed from `list[dict]` to `PaginatedResult`.**
  Callers that iterate the return value directly (`for e in client.query(...)`) must update
  to iterate via `.items` (`for e in client.query(...).items`). The `PaginatedResult` object
  exposes `items: list[dict]`, `total: int`, `limit: int`, and `offset: int`. `total`
  reflects the count of all matching entities before `limit`/`offset` are applied — callers
  can use this to implement pagination UI without a separate count query.

### New Features

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
  Raised by `client.supersede_entity()` when the source entity is already superseded.
  Attributes: `entity_id`, `superseded_by`.

- **`superseded_by` system field on all entities.**
  `client.get()` now returns `superseded_by` in the entity dict. The value is the ID of the
  replacement entity if superseded, or `None` otherwise. `hippo migrate` adds this column to
  all entity tables via `ALTER TABLE ... ADD COLUMN superseded_by TEXT` (nullable, no default).
  Pre-existing rows are unaffected (they receive `NULL`).

- **`entity_provenance_summary` view created by `hippo migrate`.**
  This view is now required (not optional) and is created before entity table migrations.
  It provides efficient batch derivation of `created_at` and `updated_at` for `client.query()`.

### Behaviour Changes

- **`client.get()` and `client.query()` now return provenance-derived `created_at` and
  `updated_at`** (authoritative source per spec). Previously these were read directly from
  entity table columns. The entity table columns are now treated as a write-through cache;
  they are still updated on every write operation but reads derive values from the provenance
  log. The values are identical for new entities but may differ in rare cases where entity
  table columns were stale.

- **`client.get()` now returns superseded entities** (those with `is_available = false` due
  to supersession). Previously a superseded entity would raise `EntityNotFoundError`. Now it
  returns the entity dict with `superseded_by` populated.

- **`client.history()` now works on superseded entities.** Previously history could not be
  fetched for entities that had been soft-deleted or superseded.
