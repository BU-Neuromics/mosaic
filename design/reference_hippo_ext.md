## Reference: `hippo_ext` Annotation Vocabulary

**Document status:** Draft v0.1
**Depends on:** sec9_linkml_redesign.md §9.4, `src/hippo/schemas/hippo_ext.yaml`

This document is the authoritative per-annotation reference for `hippo_ext.yaml` —
Hippo's formal declaration of every `hippo_*` annotation recognized by the schema
pipeline. Every `hippo_*` annotation used in any Hippo-managed schema MUST be
declared here; undeclared annotations, value-type mismatches, and wrong-target
attachments fail at schema load. See sec9 §9.4 for the design rationale.

The live schema lives at `src/hippo/schemas/hippo_ext.yaml` and ships with the
Hippo Python package. `SchemaRegistry` loads it at startup and validates every
`hippo_*` annotation in the merged user schema against the declarations below.

---

### Modeling note

LinkML has no native metamodel for declaring a vocabulary of allowed annotation
tags. `hippo_ext` repurposes LinkML's `slot` declaration as the container for
each annotation's metadata. Each `hippo_*` annotation is declared as a slot with:

- `range` — the annotation's value type (boolean, string, enum, etc.)
- `description` — human-readable semantics
- `ifabsent` — the value assumed when the annotation is omitted on an element
- `in_subset` — encodes the `applies_to` target: `slot_annotation` means the
  annotation may attach only to a LinkML `slot`; `class_annotation` means only
  to a `class`.

User schemas do not import these slots as data slots. `SchemaRegistry`
introspects `hippo_ext` to obtain the vocabulary; user schemas use the
annotations via the standard `annotations:` block on their own classes / slots.

---

### Vocabulary

Five annotations are currently declared. `hippo_unique`, `hippo_index`,
`hippo_index_partial`, and `hippo_search` landed with Wave 1
(`hippo-ext-vocabulary`); `hippo_append_only` landed with Wave 2
(`provenance-as-linkml-class`) as a declaration — adapter enforcement
follows in `provenance-migration`. `hippo_accessor` joins the vocabulary
with Wave 3's `typed-client` — see *Deferred annotations* below.

#### `hippo_unique`

| Attribute | Value |
|---|---|
| Applies to | slot |
| Value type | boolean |
| Default | `false` |
| Consumer | DDL generators (SQLite, PostgreSQL) |

Emit a single-column `UNIQUE` constraint for the annotated slot at the storage
layer. For composite uniqueness spanning multiple slots, use LinkML's native
`unique_keys` on the class — not this annotation.

**Example.**
```yaml
classes:
  Sample:
    attributes:
      barcode:
        range: string
        annotations:
          hippo_unique: true
```

#### `hippo_index`

| Attribute | Value |
|---|---|
| Applies to | slot |
| Value type | boolean |
| Default | `false` |
| Consumer | DDL generators |

Emit a single-column index for the annotated slot. Interacts with
`hippo_index_partial`.

**Example.**
```yaml
classes:
  Sample:
    attributes:
      collected_at:
        range: datetime
        annotations:
          hippo_index: true
```

#### `hippo_index_partial`

| Attribute | Value |
|---|---|
| Applies to | slot |
| Value type | boolean |
| Default | `false` |
| Consumer | DDL generators |
| Requires | `hippo_index: true` on the same slot |

When `hippo_index` is true on the same slot, emit the index as partial with
the predicate `WHERE is_available = 1`. Has no effect when `hippo_index` is
false (but SchemaRegistry does not currently warn about this combination).

**Example.**
```yaml
classes:
  Aliquot:
    attributes:
      external_id:
        range: string
        annotations:
          hippo_index: true
          hippo_index_partial: true
```

#### `hippo_search`

| Attribute | Value |
|---|---|
| Applies to | slot |
| Value type | string (free-form; adapter validates) |
| Default | *(none)* |
| Consumer | FTS DDL planner in the SQLite adapter |

Include the annotated slot in a full-text search index of the declared mode.
The mode value is a free-form string — the adapter is the authority on which
modes it supports, and MUST fail at startup with a clear error when it cannot
serve the requested mode. Schema-level validation does not constrain the
value; per sec9 §9.10, schemas declare intent and adapters enforce
capability. Current canonical mode: `fts5` (SQLite FTS5).

**Example.**
```yaml
classes:
  Sample:
    attributes:
      description:
        range: string
        annotations:
          hippo_search: fts5
```

#### `hippo_append_only`

| Attribute | Value |
|---|---|
| Applies to | class |
| Value type | boolean |
| Default | `false` |
| Consumer | Storage adapter write-guard |

Classes annotated `hippo_append_only: true` are append-only: the storage
adapter MUST reject `UPDATE` and `DELETE` against rows of the class. Only
`INSERT` is permitted. Enforcement is a runtime check in the adapter;
LinkML annotations declare intent, adapters honor it. Applied in
`hippo_core` to `ProvenanceRecord` (see `reference_hippo_core.md`).

Scope note: this annotation was introduced in Wave 2's
`provenance-as-linkml-class` as a declaration. The concrete adapter-side
enforcement (rejecting `UPDATE` / `DELETE` on `ProvenanceRecord`'s
backing table) lands with the subsequent `provenance-migration` change
per Decision 9.6.A.

**Example.**
```yaml
classes:
  ProvenanceRecord:
    is_a: Entity
    annotations:
      hippo_append_only: true
```

---

### Deferred annotations

The following annotation is part of the target vocabulary in sec9 but is
introduced by a later OpenSpec change — declared alongside its consumer,
per Decision 9.4.B in `sec9_decisions.md`.

| Annotation | Applies to | Introduced by | Wave |
|---|---|---|---|
| `hippo_accessor` | class | `typed-client` | 3 |

Not currently declared in `hippo_ext.yaml`. Using it in a user schema
before `typed-client` lands will fail at schema load with an
undeclared-annotation error.

---

### Version discipline

`hippo_ext` declares a `version:` attribute (currently `0.2.0`). Bump rules
(per sec9 §9.3):

| Change | Bump |
|---|---|
| Add an annotation | Minor |
| Add a permissible value to `hippo_search_mode` or another enum | Minor |
| Refine or clarify description text | Patch |
| Rename or remove an annotation | Major — requires an OpenSpec proposal scoping the migration |
| Change an annotation's value type, `applies_to`, cardinality, or default | Major |

`hippo_core` declares which `hippo_ext` major version it targets. A running
Hippo instance pins a specific `(hippo_ext, hippo_core)` pair; user schemas
are validated against that pair before any data operation.

---

### Adding a new annotation

Per sec9 §9.4 *Extensibility*, adding a new annotation is a four-step change,
scoped in an OpenSpec proposal:

1. Declare the annotation in `hippo_ext.yaml` — add a slot with `range`,
   `description`, `ifabsent`, and `in_subset`.
2. Implement the consumer in the subsystem that reads the annotation
   (DDL generator, validator, typed-client generator, etc.).
3. Add the annotation to this reference document with its usage example.
4. Bump `hippo_ext`'s minor version.

Removing or renaming an annotation bumps the major version and requires the
OpenSpec proposal to scope the migration path for user schemas using the
affected annotation.

---

### What `hippo_ext` does NOT declare

Some capabilities intentionally have no `hippo_*` annotation because LinkML
covers them natively. An agent implementing a user schema should reach for
the LinkML-native attribute first and only use a `hippo_*` annotation when no
LinkML equivalent exists.

| Concept | LinkML-native mechanism |
|---|---|
| Default value | `ifabsent: <literal>` or `ifabsent: uuid()`, `datetime(now)`, `int(0)`, etc. |
| Composite uniqueness | `unique_keys` on the class |
| Required slot | `required: true` |
| Pattern constraint | `pattern: "^..."` |
| Range constraint | `minimum_value: 0`, `maximum_value: 100` |
| Multivalued slot | `multivalued: true` |
| Enum membership | `range: <enum>` with `permissible_values` |
