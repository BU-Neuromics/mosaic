# `hippo_ext` Extension Vocabulary

## Why

Hippo's `hippo_*` annotations (`hippo_unique`, `hippo_index`, `hippo_index_partial`, `hippo_search`, `hippo_append_only`, `hippo_summary_view`, `hippo_accessor`) currently live as stringly-typed keys inside LinkML `annotations:` blocks on user schemas. There is no formal declaration, no typed values, no `applies_to` constraint, and no versioning. Adding a new annotation is a convention, not a contract; misspelling an annotation silently does nothing.

sec9 §9.4 formalizes the vocabulary as a shipped-with-Hippo LinkML schema (`hippo_ext.yaml`) that every `hippo_*` annotation must be declared in. Every use is validated at `SchemaRegistry` load time against this declaration.

This change is Wave 1 change #1 per sec9 §9.12 — foundation, no other changes depend on LinkML primitives yet. No observable SDK behavior changes; this is strictly a load-time validation improvement.

## What Changes

### New schema: `hippo_ext.yaml`

A LinkML schema shipped with Hippo that declares every supported `hippo_*` annotation. Ships alongside Hippo's Python package; imported by `hippo_core` (introduced in the follow-on change) and transitively by every user schema.

Each declared annotation carries:

| Attribute | Purpose |
|---|---|
| `name` | Literal annotation key (e.g., `hippo_index`). |
| `value_type` | LinkML type of the value (boolean, string, integer, enum). |
| `applies_to` | Which LinkML element types accept this annotation (class, slot, enum, permissible_value). |
| `cardinality` | Singleton or multivalued on a given element. |
| `default` | Value assumed when omitted, if any. |
| `description` | Human-readable semantics. |

### Initial vocabulary

| Annotation | Applies to | Value type | Default | Purpose |
|---|---|---|---|---|
| `hippo_unique` | slot | boolean | `false` | Single-column `UNIQUE` constraint. |
| `hippo_index` | slot | boolean | `false` | Single-column index. |
| `hippo_index_partial` | slot | boolean | `false` | Makes `hippo_index` a partial index with `WHERE is_available = 1`. No effect unless `hippo_index: true`. |
| `hippo_search` | slot | enum (`fts5`) | *(none)* | Include in a full-text index of the declared mode. |
| `hippo_append_only` | class | boolean | `false` | Storage adapter MUST reject updates and deletes on rows of this class. |
| `hippo_summary_view` | class | string | *(none)* | Emit a summary view of the named shape alongside the entity table. |
| `hippo_accessor` | class | string | *(derived)* | Override the typed-client accessor name (see 9.8). Optional escape hatch. |

### New reference doc: `design/reference_hippo_ext.md`

Authoritative per-annotation reference: default values, exact enum ranges, interactions between annotations (e.g., `hippo_index_partial` depends on `hippo_index`), and upgrade discipline.

### `SchemaRegistry` validation hook

At load time, `SchemaRegistry` walks every `annotations:` block in the merged `SchemaView` and validates each `hippo_*` key against `hippo_ext`:

- Undeclared annotation → load error naming the offending key and pointing at `hippo_ext`.
- Value type mismatch → load error with expected and actual types.
- `applies_to` violation (annotation attached to a wrong element kind) → load error naming the offending attachment.

Missing annotations fall back to their declared default. Annotations without a default are treated as "not set."

### Tests

- Declared annotations on valid targets pass.
- Undeclared `hippo_*` keys surface as load errors with helpful messages.
- Type-mismatched values fail (e.g., `hippo_index: "yes"` when value_type is boolean).
- Wrong `applies_to` fails (e.g., `hippo_append_only` on a slot).
- Every existing `hippo_*` usage in the codebase's schemas validates successfully.

## Capabilities

### New Capabilities

- `hippo-ext-vocabulary` — `hippo_ext.yaml` schema and its declaration contract.
- `annotation-validation` — `SchemaRegistry`-level validation of `hippo_*` uses against `hippo_ext`.

### Modified Capabilities

- `hippo-data-model` — documents that every `hippo_*` annotation has a formal declaration in `hippo_ext`.

## Open Questions

None for this change — all design questions are resolved in sec9 §9.4.

## Impact

- **New files:** `src/hippo/schemas/hippo_ext.yaml` (or wherever Hippo ships its schemas), `design/reference_hippo_ext.md`.
- **Modified:** `SchemaRegistry` gains a `_validate_hippo_annotations()` method called at load time.
- **No SDK behavior change.** Existing schemas that use declared annotations correctly load unchanged. Schemas with typos or undeclared annotations fail loudly where they previously failed silently.
- **No data migration.** Stored data is untouched.
- **Test suite grows** by coverage for the validation hook.

## Dependencies

- **Blocks:** `hippo-core-schema` (the follow-on change that introduces `Entity`, `Status`, `Operation`, etc. in `hippo_core.yaml`, which imports `hippo_ext`).
- **Blocked by:** nothing in sec9. This is the foundation.

## Acceptance

- `hippo_ext.yaml` exists, declares all seven initial annotations with full metadata.
- `reference_hippo_ext.md` documents each annotation authoritatively.
- `SchemaRegistry` validates every `hippo_*` usage on schema load; undeclared, mistyped, or wrongly-targeted annotations fail loudly with actionable error messages.
- Every existing `hippo_*` usage across the Hippo codebase validates successfully against `hippo_ext` without any schema edits (modulo any annotations that need to be formally declared — all current usages SHOULD match the initial vocabulary above).
- Test suite covers declared / undeclared / mistyped / wrong-target cases.
