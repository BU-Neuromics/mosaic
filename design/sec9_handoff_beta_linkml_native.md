# sec9 Handoff — β Refactor: Finish LinkML-Native Migration

**Date:** 2026-05-13
**Target completion:** ~2–3 weeks of focused engineering
**Closes:** Issue #1 (`hippo validate` is a stub)
**Defers to planned issues:** #2, #3, #4, #5 (all labeled `planned`; do not pick up)

---

## TL;DR

Finish hippo's migration to a LinkML-native storage and ingest stack. Specifically: (a) replace the legacy generic `entities (id, type, data_blob)` table with per-class typed tables; (b) replace the EntityYAML wrapper format with LinkML-native instance YAML; (c) delegate SQL DDL emission to LinkML's `SQLTableGenerator` (with a thin hippo wrapper for FTS5, partial indexes, and system columns); (d) model `ExternalID` as a first-class LinkML class instead of a hand-coded side table; (e) tighten the `EntityStore` adapter protocol so a future `LinkMLStoreAdapter` (issue #2) is a drop-in.

Adopting `linkml-store` itself is **out of scope** for this work — see issue #2 for the future α path. The spike report (`sec9_spike_linkml_store.md`) concluded β is the right ship-now path; α is the right destination once internal v1.0 lands.

---

## Read first

Read these in order before starting:

1. **`hippo/design/sec9_spike_linkml_store.md`** — the spike that produced the β-vs-α decision. Explains what we ruled out and why.
2. **`hippo/design/sec9_linkml_redesign.md` §9.1, §9.5, §9.6, §9.7** — broader LinkML-redesign rationale and existing decisions.
3. **`hippo/src/hippo/schemas/hippo_core.yaml`** — the LinkML schema that defines `Entity`, `ProvenanceRecord`, `Process`, etc. The output of step 4 in this handoff *modifies this file*.
4. **`hippo/src/hippo/linkml_bridge.py`** — `SchemaRegistry` and the LinkML wrapper. This is the seam everything builds on.
5. **`hippo/src/hippo/core/storage/__init__.py`** — `EntityStore` ABC, the adapter contract. This is the seam that must survive intact.
6. **GitHub Issue #1** — the user-visible target of this work. Closing it is the acceptance signal for Phase 3.

---

## Scope

### In scope

| Step | Description |
|---|---|
| 1 | Retire `EntityYAML` wrapper format (`entities: [{type, data, external_id}]`) in favor of LinkML-native instance YAML (tree-root pattern). |
| 2 | Per-class typed tables for domain entities — drop the legacy generic `entities (id, entity_type, is_available, version, data)` table. SDK writes go to `<ClassName>` tables. |
| 3 | Delegate SQL DDL emission to LinkML's `SQLTableGenerator`; hippo wraps for FTS5 virtual tables, partial indexes, system columns (`is_available`, `superseded_by`), and `hippo_append_only` triggers. |
| 4 | `ExternalID` becomes a LinkML class in `hippo_core.yaml` (`is_a: Entity`). The hand-coded `external_id_store` and `external_ids` table retire; lookups go through normal entity machinery. |
| 5 | Tighten `EntityStore` protocol: drop `Generic[T] = SQLiteEntity` typing leak; accept `SchemaRegistry` in adapter constructor; verify SDK has no `isinstance(adapter, …)` checks. |
| 6 | Stub `hippo/src/hippo/core/storage/adapters/linkml_store_adapter.py` declaring `LinkMLStoreAdapter(EntityStore)` with `NotImplementedError` bodies — documents the future plug-in point for issue #2. |
| 7 | Close Issue #1: `hippo validate --schema` runs `SchemaRegistry.from_path()`; `hippo validate --data` validates LinkML-native instance YAML; `hippo ingest` consumes LinkML-native YAML. |

### Out of scope

- **Do not adopt `linkml-store`** as a runtime dependency for storage. Issue #2 (`planned`) tracks this for the future α work.
- **Do not file upstream PRs** to `linkml-store` or `linkml` as part of this work. Issues #3 and #4 (`planned`) track those at hippo's pace.
- **Do not probe Postgres or Neo4j backends.** Issue #5 (`planned`) tracks spike follow-ups.
- **Do not touch `core/storage/migration.py` or `schema_diff.py`** beyond the surface area required by steps 2 and 3. These remain hippo-owned (linkml-store has no migration support; see spike §11).
- **Do not change the REST / GraphQL transport layers** beyond what the storage changes force.
- **Do not introduce CSV/JSON/SQL loader changes.** EntityYAML retirement is the only ingest-format change in scope.

---

## Architecture invariants

These must remain true after every PR in this work. The agent should reject its own changes that violate any of them.

1. **`EntityStore` is the adapter contract.** The SDK (`HippoClient`) consumes `EntityStore` only. No `isinstance(adapter, SQLiteAdapter)` anywhere above `core/storage/`. No reaching into adapter internals (`adapter._provenance_store.x` etc.).
2. **Provenance is unconditional.** Every entity write produces a `ProvenanceRecord` in the same transaction. This is true today; do not weaken it.
3. **No hard deletes.** Availability transitions via `is_available` boolean; soft-delete semantics preserved (sec9 §9.7).
4. **Closed-schema validation.** Every write passes through the existing `WriteValidator` chain → `SchemaRegistry.validate()` → LinkML closed-schema check. No write bypasses validation.
5. **`hippo_append_only` is enforced.** `ProvenanceRecord` and any other class annotated `hippo_append_only: true` must reject UPDATE and DELETE at the adapter layer.
6. **Schema-driven, not config-driven.** Class names, slot names, ranges, and relationships are read from the LinkML `SchemaView` — never hardcoded.
7. **Hippo annotations are validated.** All `hippo_*` annotations must continue to validate against `hippo_ext.yaml` at registry construction time. See `linkml_bridge.py:_validate_hippo_annotations`.
8. **System columns live on the schema, not in code.** `is_available` and `id` are declared on `Entity` in `hippo_core.yaml`. The DDL wrapper adds `superseded_by` (no LinkML equivalent yet) until issue #4 lands.

---

## Phased work plan

Three phases, each PR-sized at the boundaries. Phases must land in order — Phase 2 reads the schema changes from Phase 1; Phase 3 reads the storage shape from Phase 2.

### Phase 1: Schema-level groundwork (Steps 3, 4, 5, 6)

**Goal:** establish the schema and protocol shape that Phase 2 will write against. No SDK-visible behavior changes; the legacy `entities` table still exists.

**Suggested PR boundaries** — one PR per:

- **PR 1.1 — `ExternalID` LinkML class (Step 4).**
  - Add `ExternalID` class to `hippo_core.yaml` with slots: `id` (identifier, UUID), `value` (the source-system ID string), `source_system` (string), `entity` (range Entity, the target), `is_active` (boolean, default true). `is_a: Entity`.
  - Mark `value` as `hippo_index: true` for lookup performance; `(source_system, value)` should also be unique within active records — add `unique_keys:` block.
  - Update `Operation` enum: keep `external_id_add` / `external_id_remove` (now reference `ExternalID` instances).
  - **Do not** delete the legacy `external_id_store` yet. Phase 2 migrates writes; this PR only declares the new shape.
  - **Tests:** `tests/core/test_linkml_bridge.py` should pick up the new class. Add a test that `ExternalID` is in `registry.class_names()`.

- **PR 1.2 — Delegate DDL to LinkML's `SQLTableGenerator` (Step 3).**
  - Replace the body of `hippo/src/hippo/core/storage/ddl_generator.py:DDLGenerator.generate()` with a thin wrapper:
    1. Call `linkml.generators.sqltablegen.SQLTableGenerator(schema).generate_ddl()` to get base DDL.
    2. Post-process for hippo extras:
       - Inject `superseded_by TEXT NULL` on every per-class table that doesn't already declare it.
       - Emit `CREATE INDEX … WHERE is_available = 1` for slots annotated `hippo_index_partial: true`.
       - Emit FTS5 virtual tables for slots annotated `hippo_search: fts5`.
       - Emit triggers (SQLite) rejecting UPDATE/DELETE on tables for classes annotated `hippo_append_only: true`.
    3. Topological FK ordering: trust LinkML's output. Only re-sort if a test demonstrates it's required.
  - The `FTSMigrationPlanner` and FTS-emission code in `ddl_generator.py` can stay; just rewire to call the wrapper.
  - **Tests:** `tests/core/test_ddl_generator.py` — most tests should pass unchanged. Update any that assert exact DDL string output (the LinkML output differs in whitespace/ordering from hippo's hand-rolled version).
  - **Verification:** existing DDL output for `hippo_core.yaml` classes should produce equivalent tables (same columns, same constraints, same indexes) before/after. Compare via `EXPLAIN`/`PRAGMA table_info`, not raw string diff.

- **PR 1.3 — Tighten `EntityStore` protocol (Step 5).**
  - In `hippo/src/hippo/core/storage/__init__.py`:
    - Change `class EntityStore(ABC, Generic[T])` → `class EntityStore(ABC)`. Drop the `T` type parameter throughout. Use `dict[str, Any]` for entity records, or introduce a `EntityRecord` `TypedDict` if more structure helps. **Decision: prefer plain `dict[str, Any]` — keep this simple.**
    - Update `SQLiteAdapter`, `PostgresAdapter` to match. `SQLiteEntity` and `PostgresEntity` can stay as internal helpers but should not appear in the public protocol signature.
    - Add `schema_registry: SchemaRegistry` as a required `__init__` parameter to `EntityStore` (and concrete adapters). Pass it through from `HippoClient` (already constructed there from user schema dir).
  - **Verify** no `isinstance(adapter, SQLiteAdapter)` calls anywhere in `hippo/src/hippo/core/client.py`, `hippo/src/hippo/cli/`, `hippo/src/hippo/serve/`. `grep -rn "isinstance.*Adapter"` should show no production code matches.
  - **Tests:** existing adapter tests should pass after threading `schema_registry` through their fixtures. Anything that grabs `SQLiteAdapter.<internal>` needs to be rewritten against the protocol or moved to `tests/core/storage/test_sqlite_adapter_internals.py` (a new, clearly-internal-only file).

- **PR 1.4 — Stub `LinkMLStoreAdapter` (Step 6).**
  - Create `hippo/src/hippo/core/storage/adapters/linkml_store_adapter.py`:
    - Declare `class LinkMLStoreAdapter(EntityStore)` with all abstract methods raising `NotImplementedError("Reserved for future Option α adoption — see GitHub Issue #2")`.
    - Module docstring references issue #2 and `sec9_spike_linkml_store.md`.
  - Do **not** register the adapter anywhere or attempt to import `linkml_store`.
  - **Tests:** none required; this is a documentation stub.

**Phase 1 acceptance criteria:**
- All existing tests pass.
- `EntityStore` is no longer generic; `schema_registry` is a required constructor argument.
- `hippo_core.yaml` declares `ExternalID`.
- `ddl_generator.py` produces equivalent tables to before, but via `SQLTableGenerator` underneath.
- `linkml_store_adapter.py` exists as a stub.

---

### Phase 2: Storage migration (Step 2)

**Goal:** SDK writes go to per-class typed tables. Drop the legacy `entities` blob table. ExternalID migrates to its new class-backed shape.

**This is the biggest phase.** It changes how `HippoClient.put/read/query` work internally and touches every adapter method.

**Suggested PR boundaries:**

- **PR 2.1 — Per-class table emission and writes.**
  - `SQLiteAdapter._init_database()` should call the new `DDLGenerator` (from PR 1.2) for the user schema, emitting per-class tables.
  - Rewrite `SQLiteAdapter.create()` / `read()` / `update()` / `delete()` / `find()` to operate on the per-class table for `data["entity_type"]` instead of the generic `entities` table.
  - The legacy `entities` table creation in `sqlite_adapter.py:970–986` can stay temporarily during migration; mark it `# DEPRECATED — remove in PR 2.3`.
  - **Tests:** integration tests under `tests/integration/` will need significant updates. Aim to keep tests *semantic* (assert "an entity of type X with name Y exists") rather than tied to the table layout.

- **PR 2.2 — ExternalID writes via entity machinery.**
  - Replace `ExternalIdStorageAdapter` writes with normal entity creates of `ExternalID` instances.
  - `register_external_id(entity_id, value, source_system)` becomes: `client.put("ExternalID", {"value": ..., "source_system": ..., "entity": entity_id, "is_active": True})` + a `ProvenanceRecord` with operation `external_id_add`.
  - `get_by_external_id(value, source_system)` becomes a query against the `ExternalID` table joined on `is_active = 1`.
  - `supersede_external_id(...)` becomes a soft-update: set `is_active = false` on the old row, create a new row, link via provenance with operation `supersede`.
  - Update `provenance_service.py:206–280` and adjacent paths.
  - **Tests:** `tests/core/test_external_id.py`, `tests/core/test_external_id_client.py`. Behavior should be unchanged at the API level (`client.register_external_id` etc. still work the same way).

- **PR 2.3 — Drop legacy `entities` table and `external_ids` table.**
  - Remove the `CREATE TABLE IF NOT EXISTS entities (...)` block from `sqlite_adapter.py`.
  - Remove the `external_ids` table creation.
  - Remove `ExternalIdStorageAdapter` class.
  - Anything that still reads from `entities` or `external_ids` after this PR is a bug — fix it.
  - **Tests:** full integration suite. If a test references the `entities` table directly via SQL, rewrite it to go through the SDK.

- **PR 2.4 — `_entity_registry` shadow table for cross-class UUID lookup.**
  - With per-class tables, `client.read(uuid)` can't scan one table. Two options were discussed:
    - (a) Maintain a `_entity_registry(uuid PRIMARY KEY, class_name TEXT NOT NULL)` table updated by post-insert hooks. Fast lookup.
    - (b) Query `ProvenanceRecord` for `(entity_id = uuid)` and read `entity_type`. Slower but no extra table.
  - **Decision: implement (a).** It's small, it's fast, and it's what sec9 implies.
  - Add the table to `_init_database()`. Maintain it in `create()` / supersede paths.
  - **Tests:** add `test_cross_class_uuid_lookup` covering "I have a UUID and don't know the class — give me the entity."

**Phase 2 acceptance criteria:**
- No row anywhere in any test DB ends up in a legacy `entities` or `external_ids` table.
- All existing functional tests pass.
- `client.read(uuid)` works without the caller knowing the class.
- ProvenanceRecord still records every write.

---

### Phase 3: Wire format + Issue #1 closure (Steps 1, 7)

**Goal:** retire EntityYAML; `hippo validate` and `hippo ingest` consume LinkML-native instance YAML; close Issue #1.

**Suggested PR boundaries:**

- **PR 3.1 — Tree-root LinkML synthesis for instance ingest.**
  - At `SchemaRegistry` construction time, synthesize a tree-root class (e.g., `_HippoInstanceBundle`) with one multivalued slot per concrete class in the schema. Slot name: snake-cased class name pluralized (or class name as-is — pick one convention and document it; sec3 §3.6 hints, decide and write it down).
  - This synthesis is internal — user schemas don't need to declare a tree root.
  - Add `SchemaRegistry.tree_root_class_name() -> str` accessor.
  - **Tests:** `tests/core/test_linkml_bridge.py` — assert the tree-root class is synthesized correctly for a sample schema.

- **PR 3.2 — `hippo validate --schema`, `--data`.**
  - Rewrite `hippo/src/hippo/cli/main.py:241–316` (the `validate` command).
    - `--schema`: call `SchemaRegistry.from_path(path)`. If it raises `SchemaError`, print errors and exit 1. If it succeeds, print "Schema is valid LinkML with N classes."
    - `--data`: load the YAML file as a dict, call `registry.validate(content, registry.tree_root_class_name())`. Print errors with file path + per-entry locations; exit 1 if any.
    - The current `--config` flag can stay as today (validates the hippo config file shape) — out of scope for this work.
  - **Tests:** rewrite `tests/integration/test_validate_cli.py` to use real LinkML schemas. Cover:
    - Valid LinkML schema passes.
    - "Garbage" schema (Test 2 from Issue #1: `{this_is_not_linkml: true, random_key: 42}`) fails with a useful error. **This is the key acceptance test for Issue #1.**
    - Valid data bundle passes.
    - Bundle missing required field (Test 5 from Issue #1) fails with field-named error.

- **PR 3.3 — Retire `EntityYAMLLoader` and `ingest_entity_file`.**
  - Delete `hippo/src/hippo/core/loaders/entity_yaml.py`.
  - Rewrite `hippo/src/hippo/cli/commands/ingest.py` to consume LinkML-native instance YAML against the tree-root class. The new function (e.g., `ingest_linkml_yaml`) loads the file, validates each entry against the appropriate target class via `registry.validate`, then writes via `client.put` per entry.
  - Add `--validate-schema PATH` option to `hippo ingest` so dry-run validation matches Phase 3.2.
  - Update `tests/cli/test_ingest.py` — rewrite all fixtures from `entities: [...]` to LinkML-native shape.
  - Delete the three "DSL" string artifacts in `cli/main.py:359`, `:366`, `:395`.
  - **Tests:** `test_ingest_*` tests should mostly survive with new fixtures.

- **PR 3.4 — Documentation.**
  - Update `hippo/README.md` "Validation Pipeline" section: the CLI path now actually validates. Show a real LinkML schema + instance YAML example.
  - Update `hippo/docs/` user-facing guides to drop EntityYAML references.
  - Update `hippo/CLAUDE.md` if any references to EntityYAML remain.

**Phase 3 acceptance criteria:**
- Issue #1 closes. The reporter's Test 2 (garbage schema → "all checks passed") now produces a real error.
- `hippo validate --schema garbage.yaml` exits non-zero.
- `hippo ingest --file <linkml-native.yaml>` works against a tree-root schema.
- `linkml-validate` (the upstream binary) can validate hippo entity files unchanged — no more wrapper-format error.
- No string "DSL" or "EntityYAML" remains in `src/hippo/` (the loader file is deleted).

---

## Decisions log

The agent should not re-litigate these. They were settled in the conversation that produced this handoff.

| Decision | Choice | Rationale |
|---|---|---|
| Storage abstraction | **β: delegate DDL to LinkML's `SQLTableGenerator`; keep hand-coded adapters** | Ship velocity priority; α adoption is issue #2 (post-1.0). |
| Wire format | **Tree-root LinkML instance YAML** | Most ergonomic; matches LinkML tutorials; `linkml-validate` works directly. |
| ExternalID modeling | **Option D: first-class LinkML class on `hippo_core.yaml`** | Sec3 §3.4 already designs it as lifecycle-tracked identity. Modeling it as a class is the LinkML-pure answer. |
| Adapter constructor | **`SchemaRegistry` is a required parameter** | Future `LinkMLStoreAdapter` needs the same signature. |
| Cross-class UUID lookup | **`_entity_registry(uuid, class_name)` shadow table** | Faster than scanning ProvenanceRecord; sec9 implies this name already. |
| Append-only enforcement | **SQLite triggers (β); future adapter overrides (α)** | Both backends honor `hippo_append_only` at the storage layer. |
| Schema migration | **Stays hippo-owned (`schema_diff.py`, `migration.py`)** | linkml-store has zero migration support; α doesn't change this. |
| `EntityStore` typing | **Drop `Generic[T]`; use `dict[str, Any]`** | Keep the protocol simple; backend-agnostic. |
| Linkml-store adoption | **Stubbed only as future plug-in (`LinkMLStoreAdapter`)** | Real adoption is issue #2. β stubs the file to document intent. |
| Tree-root slot naming (PR 3.1) | **`snake_case(ClassName) + "s"`, honoring `hippo_accessor` overrides; tree-root class held off the SchemaView** | Aligns the wire format with the typed-client accessor surface so users see one convention. Holding the synthetic class off the SchemaView keeps DDL/diff/typed-client unaware of it. Bundled fix: `hippo_accessor: processes` on `Process` to avoid the `processs` (triple-s) plural. |

---

## What "done" looks like

After all three phases land:

1. Issue #1 is closed by PR 3.2.
2. `hippo validate --schema garbage.yaml` reports a real LinkML error and exits non-zero.
3. `linkml-validate` from the upstream `linkml` package can validate hippo entity files without needing the wrapper format unwrapped.
4. `hippo` has no `EntityYAML`, no `entities: [...]` wrapper, no string `DSL` anywhere in `src/`.
5. Every domain class has its own SQL table; the generic `entities` blob table is gone.
6. `ExternalID` is a normal entity class — same write path, same provenance, same query semantics.
7. `EntityStore` is the only interface between SDK and storage; no SQLite-specific leaks.
8. `LinkMLStoreAdapter` exists as a stub for the future α work (issue #2).
9. The full integration test suite passes.
10. Documentation reflects the new wire format.

---

## Gotchas / known traps

- **`hippo_core.yaml` is loaded as a bundled resource via `importlib.resources`** (see `linkml_bridge.py:_hippo_core_resource_path`). Changes to the file are picked up at runtime, but the package install path matters — verify edits propagate via `uv run` rather than `python`.
- **Schema version field in `ProvenanceRecord` is required** (`schema_version` slot is `required: true`). Every write — including the new ExternalID writes — must populate it. `SQLiteAdapter` already threads it from the registry; verify the path survives the Phase 2 rewrite.
- **The `entities` table appears in raw SQL strings inside FTS triggers** in `sqlite_adapter.py:1191` (`content_table: str = "entities"`). FTS5 content tables reference the source table by name. When per-class tables replace `entities`, the FTS planner must emit per-class FTS triggers.
- **Tests under `tests/integration/test_validate_cli.py` use a made-up schema format** (`name`, `entities[*].properties`) that was never real LinkML. Phase 3 must rewrite these tests against real LinkML schemas. Don't assume they're correct — they were testing the *stub* behavior.
- **The reporter's Test 5 in Issue #1's comments** (entity missing required `name` field) is the most concrete acceptance test. Use that exact fixture as a regression test in PR 3.2.
- **`PydanticGenerator` is already used in `typed_client.py:459`.** No changes needed there — but verify it still works after Phase 1's DDL delegation. Pydantic generation and SQL generation are independent code paths.

---

## Pointers to related work

- **GitHub Issue #1** — the user-visible target. Updates as PRs land.
- **GitHub Issue #2** (`planned`) — future α adoption of `linkml-store`. Do not pick up.
- **GitHub Issue #3** (`planned`) — upstream `linkml-store` contributions. Do not pick up.
- **GitHub Issue #4** (`planned`) — upstream `LinkML SQLTableGenerator` contributions. Do not pick up.
- **GitHub Issue #5** (`planned`) — spike follow-ups (Postgres, Neo4j, benchmark). Do not pick up.
- **`hippo/design/sec9_spike_linkml_store.md`** — the spike that justifies β over α.
- **`hippo/design/sec9_linkml_redesign.md`** — broader sec9 design context.
- **`hippo/spike/linkml-store/`** — throwaway spike probe scripts. Safe to delete after β lands.
