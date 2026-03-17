# Entity Namespaces

## Why

As BASS grows, a single `schema.yaml` becomes unwieldy. Different subsystems (Subject, Tissue, Omics, Compute) need to evolve independently, be owned by different teams, and potentially be deployed in subsets. Without namespacing, entity type names are globally flat, cross-team naming collisions are inevitable, and there is no structural way to express that `tissue.Sample` is a different concept from `omics.Sample`.

## What Changes

### Namespace declaration in schema files

Each schema file may declare a `namespace` key at the top level. Files without this key contribute entities to the **root namespace**.

```yaml
# schemas/tissue.yaml
namespace: tissue
entities:
  - name: Sample
    fields: [...]
```

```yaml
# schemas/legacy.yaml
# no namespace key → root namespace
entities:
  - name: Donor
    fields: [...]
```

Multiple files may share the same namespace — their entity lists are merged at load time. The schema loader recurses into the `schemas/` directory tree without using directory names to infer namespaces.

### Fully-qualified entity type names (FQN)

The entity type of `Sample` in namespace `tissue` is `tissue.Sample`. The entity type of `Donor` in the root namespace is `Donor` (or equivalently `root.Donor`). Root is the only implicit namespace; all others must be explicit.

- `tissue.Sample` — namespaced entity
- `Donor` — root namespace entity (shorthand)
- `root.Donor` — root namespace entity (explicit form, equivalent to above)
- No configurable default namespace

FQNs are used everywhere an entity type is named: `client.put("tissue.Sample", {...})`, `GET /entities?entity_type=tissue.Sample`, cross-namespace references in schema fields.

### Cross-namespace references

Schema fields reference entities in other namespaces using the FQN in the `references.entity_type` key:

```yaml
# schemas/tissue.yaml
namespace: tissue
entities:
  - name: Sample
    fields:
      - name: donor_id
        type: string
        references:
          entity_type: Donor        # root namespace (unqualified)
      - name: parent_sample_id
        type: string
        references:
          entity_type: tissue.Sample  # same namespace, explicit FQN
```

### Dependency inference and validation

Namespace dependencies are **inferred** at parse time from FQN references — no explicit `depends_on` declaration required. The schema validator:

1. Builds the full namespace registry from all discovered schema files
2. For each cross-namespace reference, checks that the referenced namespace and entity type exist
3. Raises `SchemaValidationError` if a referenced namespace or entity is not found
4. Detects circular namespace dependencies and raises an error

This validation runs at `hippo migrate` time and also via `hippo validate --schema`.

### Backwards compatibility

Existing schemas with no `namespace:` key continue to work unchanged. All previously-unqualified entity types are in the root namespace. `client.put("Sample", {...})` remains valid and resolves to the root `Sample` entity. No data migration is required for existing deployments.

### HippoClient API

No changes to method signatures. The `entity_type` parameter already accepts a string — callers simply pass FQNs when working with namespaced entities:

```python
client.put("tissue.Sample", {"id": "s001", "donor_id": "d001"})
client.get("tissue.Sample", "s001")
client.query("tissue.Sample", filters=[...])
```

The storage adapter receives the FQN as-is. The SQLiteAdapter stores it verbatim in the `entity_type` column, meaning `tissue.Sample` and `omics.Sample` are already distinct entity types in storage with no adapter changes required.

### CLI

`hippo migrate` discovers and loads all schema files recursively, resolves namespaces, validates cross-namespace references, and applies migrations. The `--schema-dir` flag continues to work as the root of discovery.

`hippo validate --schema` also resolves and validates the full namespace graph.

---

## Capabilities

### New Capabilities
- `schema-namespaces` — multi-file schema loading, namespace registry, FQN resolution, cross-namespace reference validation

### Modified Capabilities
- `schema-compilation-and-validation` — namespace-aware validation during `hippo migrate` and `hippo validate`
- `hippo-data-model` — entity type strings are now optionally namespace-qualified; root namespace semantics

---

## Open Questions

### ⚠️ Entity type migration / namespace remapping (deferred)

If an existing root-namespace entity (`Sample`) needs to move to a namespace (`tissue.Sample`), there is currently no supported migration path. This is a non-trivial rename of entity type across all rows in storage and all provenance records.

Options to address later:
- `hippo migrate --remap Sample tissue.Sample` — explicit opt-in remap command
- Namespace aliasing — `tissue.Sample` as an alias for `Sample` during a transition period
- Out-of-band data migration script

**This must be addressed before any team attempts to namespace-migrate a production dataset.**

---

## Impact

- New `SchemaLoader` / `NamespaceRegistry` component in `hippo/config/` or `hippo/core/`
- `hippo migrate` and `hippo validate` updated to use namespace-aware loader
- No storage adapter changes required
- No `HippoClient` method signature changes
- No REST API changes
- Existing single-file `schema.yaml` deployments continue to work unchanged
