# `hippo_core` Schema — Hippo Primitives as a LinkML Schema

## Why

Hippo's own primitives — `Entity`, `Status`, `Operation`, `Validator`, `ReferenceLoader` — currently live as Python constructs that a hand-written DDL path produces tables for. They are not declared in any LinkML schema; they cannot be introspected through `SchemaRegistry`; they don't benefit from `gen-sqlddl`, `gen-pydantic`, `linkml-validate`, or `linkml-diff`; and user schemas have no way to express `is_a: Entity` because there is no `Entity` in any LinkML schema to inherit from.

sec9 §9.5 moves these primitives into a shipped-with-Hippo LinkML schema (`hippo_core.yaml`) that imports `hippo_ext` (already landed in `hippo-ext-vocabulary`) and that every user schema imports in turn. Domain classes declare `is_a: Entity` to inherit the base shape (`id` + `is_available`); enums come from `hippo_core` directly.

This change is Wave 1 change #2 per sec9 §9.12. It depends on `hippo-ext-vocabulary` (needs the annotation vocabulary declared before `hippo_core` can use annotations like `hippo_append_only`). It is strictly additive at the data-model level: existing entity tables are untouched; user schemas gain an `is_a: Entity` declaration and an `imports: hippo_core` line.

## What Changes

### New schema: `hippo_core.yaml`

A LinkML schema shipped with Hippo, imported by every user schema. Contents:

| Element | Kind | Shape |
|---|---|---|
| `Entity` | abstract class | Slots: `id` (identifier, UUID, required), `is_available` (boolean, required, default `true`). Class-uri: `prov:Entity`. |
| `Status` | enum | `active`, `archived`, `superseded`, `deleted`, `distributed`, `removed`. |
| `Operation` | enum | `create`, `update`, `availability_change`, `supersede`, `relationship_add`, `relationship_remove`, `external_id_add`, `external_id_remove`, `migration_applied`, `reference_data_installed`. |
| `Validator` | class (placeholder) | Declared but slot inventory defers to the existing `validators.yaml` shape; finalized in a later OpenSpec change. |
| `ReferenceLoader` | class (placeholder) | Declared but slot inventory deferred to `reference-loader-shape` (Wave 3). |

`ProvenanceRecord` and `Process` are NOT introduced by this change — they land in `process-class` (Wave 1 #4) and `provenance-as-linkml-class` (Wave 2) respectively. This keeps the change small and independently reviewable.

### Three-layer merge in `SchemaRegistry`

`SchemaRegistry` is updated to load the three-layer stack: `hippo_ext` → `hippo_core` → user schema. The merged `SchemaView` is the sole schema representation consumed by every downstream subsystem, per sec9 §9.3.

- Load order: `hippo_ext` first, then `hippo_core`, then user schemas.
- Import-graph validation: `hippo_core` must import `hippo_ext`; user schemas must import `hippo_core`. Missing or wrong imports are load-time errors.
- Version compatibility: `hippo_core` declares the `hippo_ext` major version it targets; user schemas declare the `hippo_core` major version they target. Mismatch is a load-time failure.

### User-schema migration: `is_a: Entity`

Every domain class in every existing user schema in the repo is updated to declare `is_a: Entity`. This is a textual edit — no data change, no code change beyond the schema YAML files.

Classes that previously declared their own `id` and `is_available` slots either remove those declarations (inherited from `Entity`) or keep them as explicit redeclarations if a deployment prefers. The former is preferred and is what existing fixtures are migrated to.

### New reference doc: `design/reference_hippo_core.md`

Per-class slot-level reference for `hippo_core`. Documents `Entity`, `Status`, `Operation`, and the placeholder shapes for `Validator` and `ReferenceLoader`. Follows the existing reference-doc template.

### Tests

- Loading a user schema without `imports: hippo_core` fails with a clear error message.
- Loading a user schema with `is_a: Entity` on every domain class passes.
- Loading a domain class that redeclares `id` or `is_available` succeeds (explicit redeclaration allowed).
- `hippo_core` loads against `linkml-validate` against the LinkML metamodel.
- Version-mismatch between `hippo_core` and installed `hippo_ext` surfaces as a load-time failure.

## Capabilities

### New Capabilities

- `hippo-core-schema` — Hippo primitives declared in a LinkML schema.
- `three-layer-schema-merge` — `SchemaRegistry` merges `hippo_ext` + `hippo_core` + user schema into one `SchemaView`.

### Modified Capabilities

- `hippo-data-model` — primitives are now LinkML-declared.
- `schema-compilation-and-validation` — import-graph and version-compatibility validation added to the schema-load path.

## Open Questions

- **Final `Validator` slot inventory.** Declared as a placeholder; full shape is deferred to a later change that reconciles with `validators.yaml`.
- **Final `ReferenceLoader` slot inventory.** Deferred to `reference-loader-shape` (Wave 3) per sec9 §9.5.

## Impact

- **New files:** `src/hippo/schemas/hippo_core.yaml`, `design/reference_hippo_core.md`.
- **Modified:** `SchemaRegistry` load path gains three-layer merge and version-compatibility check. All user schemas in `schemas/`, `tests/fixtures/`, and `docs/` gain `imports: hippo_core` and `is_a: Entity` on domain classes.
- **No data migration.** Entity tables keep their existing columns. The new `is_a: Entity` declaration doesn't change the DDL output since `id` and `is_available` were already there; it only changes the LinkML representation of the schema.
- **No SDK behavior change.** Callers continue to use the generic `HippoClient` as before.

## Dependencies

- **Blocked by:** `hippo-ext-vocabulary` (Wave 1 #1).
- **Blocks:** `id-registry-and-uuid-strategy` (Wave 1 #3), `process-class` (Wave 1 #4), `reference-loader-shape` (Wave 3).

## Acceptance

- `hippo_core.yaml` exists, validates against `linkml-validate`, and declares the full initial inventory (`Entity`, `Status`, `Operation`, placeholder `Validator`, placeholder `ReferenceLoader`).
- `SchemaRegistry` merges the three layers; load fails loudly on missing or wrong imports, and on incompatible major versions.
- Every user schema in the repo (fixtures, examples, deployment configs under version control) declares `imports: hippo_core` and uses `is_a: Entity` on every domain class.
- `reference_hippo_core.md` is published and linked from `INDEX.md`.
- Full test suite green, including new import-graph and version-compat tests.
- No observable SDK behavior change for callers.
