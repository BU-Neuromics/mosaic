## Reference: `hippo_core` — Hippo's Built-In Classes and Enums

**Document status:** Draft v0.1
**Depends on:** sec9_linkml_redesign.md §9.5, `src/hippo/schemas/hippo_core.yaml`

This document is the authoritative reference for `hippo_core.yaml` — Hippo's
built-in primitives shipped as a LinkML schema. Every user schema imports
`hippo_core` and every domain class uses `is_a: Entity`. See sec9 §9.5 for
the design rationale.

The live schema ships at `src/hippo/schemas/hippo_core.yaml` and is loaded
by `SchemaRegistry` via a bundled importmap: callers declare
`imports: [hippo_core]` in their own schemas and LinkML resolves the
reference to the shipped file.

---

### Class and enum inventory

| Element | Kind | Purpose |
|---|---|---|
| `Entity` | abstract class | Base class for every domain entity. Provides `id` and `is_available`. |
| `ProvenanceRecord` | class | Atomic audit record of an operation on an entity. Annotated `hippo_append_only: true`; PROV-O-aligned. `is_a: Entity`. |
| `Process` | class | Composite activity grouping atomic operations under one logical execution (reference loads, migrations, pipeline runs). `is_a: Entity`. |
| `Validator` | class (placeholder) | Declarative validator definition; slot inventory finalized later. |
| `ReferenceLoader` | class (placeholder) | Metadata for reference-data loader plugins; slot inventory finalized by the `reference-loader-shape` OpenSpec change. |
| `Status` | enum | Lifecycle state of an entity. |
| `Operation` | enum | Operation kinds recorded on a `ProvenanceRecord`. |

---

### `Entity`

Abstract base class. `class_uri: prov:Entity` for PROV-O alignment. Domain
classes specialize via `is_a: Entity`. Two slots:

| Slot | Type | Required | Default | Semantics |
|---|---|---|---|---|
| `id` | string (identifier) | yes | — | Stable primary key. UUID-typed per sec9 §9.5. SDK-assigned on create; opaque to callers. |
| `is_available` | boolean | yes | `true` | Lifecycle flag. `true` = entity participates in normal reads; `false` = superseded/archived/deleted/distributed/removed. The reason lives in provenance, not on the entity. |

Temporal state (`created_at`, `updated_at`, `schema_version`) is
deliberately NOT declared here — computed at read time from
`ProvenanceRecord` per sec9 §9.7. Status transitions are recorded as
`ProvenanceRecord` entries with an `availability_change` operation.

**Example.**
```yaml
# user_schema.yaml
imports:
  - hippo_core
classes:
  Sample:
    is_a: Entity
    attributes:
      barcode:
        range: string
        annotations:
          hippo_unique: true
```

---

### `ProvenanceRecord`

Atomic audit record of an operation on an entity. `is_a: Entity`
(participates in the normal identity model — UUID id, lifecycle) but
annotated `hippo_append_only: true` — adapters MUST reject `UPDATE` and
`DELETE` against the backing table. Only `INSERT` is permitted.

`class_uri: prov:Activity` at the atomic scale. `Process` shares the
same class URI at the composite scale; PROV-O treats activities at
multiple granularities uniformly.

| Slot | Type | Required | PROV-O | Semantics |
|---|---|---|---|---|
| `id` | string (UUID) | yes | — | Inherited from `Entity`. |
| `is_available` | boolean | yes | — | Inherited from `Entity`. |
| `entity_id` | string (UUID) | no | `prov:wasGeneratedBy` / `prov:wasInvalidatedBy` (operation-dependent) | UUID of the target entity. Null ONLY for system operations (`migration_applied`, `reference_data_installed`). |
| `entity_type` | string | no | — | FQN of the target entity at write time. Denormalized onto the record so audit queries can avoid a registry lookup. Null when `entity_id` is null. |
| `operation` | `Operation` enum | yes | — | Kind of operation — see the `Operation` enum below. |
| `actor_id` | string (UUID) | yes | `prov:wasAssociatedWith` | UUID of the responsible entity (user-schema agent, Process, or system entity). |
| `timestamp` | datetime | yes | `prov:endedAtTime` | UTC wall-clock time at which the operation completed. |
| `schema_version` | string | yes | — | Version of the merged schema at the moment of write. Captured by the SDK; never caller-supplied. |
| `derived_from_id` | string (UUID) | no | `prov:wasDerivedFrom` | For `supersede` operations, the previous entity version. |
| `process_id` | Process | no | `prov:wasInformedBy` (convention) | Enclosing `Process`. Used to reconstruct multi-entity activities from their atomic members. |
| `patch` | string (JSON) | no | — | Operation-specific change payload. Shape varies by operation. Unstructured by design. |
| `context` | string (JSON) | no | — | Caller-supplied contextual metadata. Structure at the caller's discretion. |

**Indexes** (via `hippo_index: true` annotations): `entity_id`,
`operation`, `timestamp`, `process_id`. Wave 2 `computed-temporal-fields`
adds composite indexes as needed for the read-time aggregation paths.

**Scope note (Decision 9.6.A).** This declaration lands with Wave 2's
`provenance-as-linkml-class`. The actual storage migration — moving
the legacy `provenance` table and `ProvenanceStore` implementation onto
this shape — is scoped as a separate `provenance-migration` OpenSpec
change. Until that change lands, the legacy `provenance` table (with its
`operation_type` / `previous_state_hash` / `state_snapshot` columns)
continues to back the existing `ProvenanceStore` API; the LinkML-declared
`ProvenanceRecord` shape is authoritative for introspection and
downstream uses (typed-client generation, REST surface, `hippo_core`
consumers).

---

### `Process`

Composite activity — a grouping of atomic operations under one logical
execution. `is_a: Entity`; `class_uri: prov:Activity` for PROV-O alignment.
Shares the class URI with `ProvenanceRecord` at the atomic scale;
PROV-O treats activities at multiple granularities uniformly.

Use cases: reference-data loads, schema migrations, Cappella pipeline runs,
batch upserts. Callers specialize via `is_a: Process` for domain-specific
attributes (pipeline parameters, input/output manifests, runtime metadata).

| Slot | Type | Required | Semantics |
|---|---|---|---|
| `id` | string (UUID) | yes | Inherited from `Entity`. |
| `is_available` | boolean | yes | Inherited from `Entity`. Processes are archived, not hard-deleted. |
| `parent_process_id` | Process (self-ref) | no | Process composition. Processes form a tree; caller can model a DAG by adding further references on subclasses. Null for root processes. |
| `operation_kind` | string | yes | Caller-defined category (`reference_data_installed`, `pipeline_run`, `schema_migration`, `manual_edit`, …). Not a closed enum. Annotated `hippo_index: true`. |
| `started_at` | datetime | yes | UTC wall-clock time at process start. Annotated `hippo_index: true`. |
| `ended_at` | datetime | no | UTC wall-clock time at process completion. Null while running or after failure without completion. |
| `actor_id` | string (UUID) | yes | UUID of the entity responsible for initiating this process. Resolvable via `HippoClient.resolve_type(uuid)` per sec9 §9.5. |

**Lifecycle via provenance (Wave 2).** Process creation emits a `create`
ProvenanceRecord (like any other entity). State transitions (setting
`ended_at`, archival via `availability_change`) emit further records.
Recursion bottoms out at root processes whose creation record has
`process_id: null`. See sec9 §9.6 for the full semantics.

**Example.**
```yaml
# Cappella schema fragment
imports:
  - hippo_core
classes:
  PipelineRun:
    is_a: Process
    attributes:
      pipeline_name:
        range: string
        required: true
      parameters:
        range: string   # JSON blob
      run_host:
        range: string
```

---

### `Status` enum

Lifecycle state of an entity. Recorded in provenance via
`availability_change` operations; not stored on the entity itself.

| Value | Description |
|---|---|
| `active` | Entity is live and participates in normal reads. |
| `archived` | Retained but not available for active use. |
| `superseded` | Replaced by another (pointer in provenance via `derived_from_id`). |
| `deleted` | Soft-deleted. Data retained; `is_available` is false. |
| `distributed` | Sent elsewhere (e.g., external distribution). |
| `removed` | Physically removed (rare; normally `superseded` / `deleted`). |

Adding a value is a minor bump on `hippo_core`. Removing a value is breaking.

---

### `Operation` enum

Kind of operation recorded on a `ProvenanceRecord`. See sec9 §9.6 for the
per-value PROV-O mapping and payload semantics.

| Value | Semantics |
|---|---|
| `create` | Entity created. |
| `update` | Entity slot values modified in place. |
| `availability_change` | `is_available` flag transitioned; new value and `Status` driver carried in the record's `patch`. |
| `supersede` | Entity superseded by another; `derived_from_id` carries the predecessor. |
| `relationship_add` | A relationship slot gained a value; `patch` carries `{slot, target_id}`. |
| `relationship_remove` | A relationship slot lost a value; `patch` carries `{slot, target_id}`. |
| `external_id_add` | An ExternalID was associated with the entity. |
| `external_id_remove` | An ExternalID was disassociated. |
| `migration_applied` | A schema migration was applied (system event; `entity_id` is null). |
| `reference_data_installed` | A reference loader installed data (system event; `entity_id` is null). |

---

### `Validator` (placeholder)

Declarative validator definition — full slot inventory is finalized in a
later OpenSpec change that reconciles this class with the existing
`validators.yaml` format. Current declared slots:

| Slot | Type | Required |
|---|---|---|
| `name` | string (identifier) | yes |

Implementation-side `validators.yaml` continues to work unchanged until
that change lands; this placeholder exists so `is_a: Validator`
user-schema extensions become possible as soon as the shape firms up.

---

### `ReferenceLoader` (placeholder)

Metadata for reference-data loader plugins. Slot inventory deferred to the
`reference-loader-shape` OpenSpec change (Wave 3 per sec9 §9.12). Two open
design questions gate the final shape:

- **Multi-class loaders.** `entity_type` must be multivalued; exact
  cardinality semantics open.
- **Referential boundary of `schema_fragment`.** A `ReferenceLoader`
  instance may reference classes declared in its own `schema_fragment`.
  The load-order contract (when the fragment is merged, when the
  instance is validated) needs deliberate design.

Current declared slots:

| Slot | Type | Required |
|---|---|---|
| `name` | string (identifier) | yes |

---

### Version and compatibility

`hippo_core.version` is `0.3.0` (0.1.0 initial → 0.2.0 added `Process` → 0.3.0 added `ProvenanceRecord`). Bump rules (per sec9 §9.3):

| Change | Bump |
|---|---|
| Add an optional slot on `Entity`, new enum value, new class | Minor |
| Change an existing class's slot shape, newly required slot, enum removal | Major |

Deployments pin a specific `(hippo_ext, hippo_core)` pair. User schemas
declare which `hippo_core` major they target; `SchemaRegistry` refuses to
merge against an incompatible major.

---

### Design invariants

Three invariants a coding agent must preserve when touching `hippo_core`:

1. **`Entity` stays sparse.** Only `id` and `is_available`. Resist adding
   slots; everything else belongs either in a user-schema subclass or
   derives from provenance.
2. **No cross-layer references.** `hippo_core` MUST NOT reference any
   domain class. Any relationship from a domain entity to its provenance
   is expressed via `entity_id` on `ProvenanceRecord` (Wave 2), never by
   a slot on `Entity` pointing into system-level data.
3. **`hippo_core` validates against itself.** Its own shape satisfies the
   LinkML metamodel. A malformed `hippo_core` is a startup failure, not a
   silent degradation.

---

### What `hippo_core` deliberately excludes

Some concepts sec9 specifies but does not land in this change. An agent
encountering a gap should consult the owning change below rather than
adding the concept to `hippo_core` ad-hoc.

| Concept | Owning change |
|---|---|
| `ProvenanceRecord` adapter-side write-guard + `ProvenanceStore` migration onto the LinkML-declared shape | `provenance-migration` (Wave 2, follow-up to `provenance-as-linkml-class` per Decision 9.6.A) |
| `superseded_by` as a proper provenance-derived relationship | `provenance-migration` (Wave 2) |
| Computed temporal fields on entity reads | `computed-temporal-fields` (Wave 2) |
| Final `Validator` slot inventory | Later OpenSpec change; deferred pending `validators.yaml` reconciliation |
| Final `ReferenceLoader` slot inventory | `reference-loader-shape` (Wave 3) |
| Typed client Pydantic generation | `typed-client` (Wave 3) |
