# Entity Namespaces — Design

## Context

Hippo's schema system currently loads entity definitions from a single flat file (`schema.yaml`). Entity type names are globally unqualified strings (e.g., `"Sample"`, `"Donor"`). As BASS grows and multiple teams evolve independent subsystems, this model breaks down: names collide, files become too large to manage, and there's no structural way to scope ownership or deployment.

This design introduces **namespaces** — a first-class concept in the schema loader that partitions entity types into named scopes. It is strictly additive: existing deployments with no `namespace:` key in their schemas continue to work unchanged.

Stakeholders: SDK team (core implementation), platform team (migration tooling), subsystem teams (tissue, omics, compute) who will adopt namespaces over time.

## Goals / Non-Goals

**Goals:**
- Allow schema files to declare a `namespace` key, scoping their entities under a named prefix
- Define FQN (fully-qualified name) semantics: `namespace.EntityType`, with root-namespace entities addressable as plain strings
- Infer namespace dependencies from cross-namespace `references.entity_type` fields — no explicit `depends_on` required
- Validate the full namespace graph at `hippo migrate` and `hippo validate --schema` time: unknown references and circular dependencies raise errors
- Merge entity lists across multiple files sharing the same namespace
- Maintain full backwards compatibility — existing schemas require no changes

**Non-Goals:**
- Namespace-to-namespace migration / entity type remapping (deferred; see Open Questions)
- Directory-path-based namespace inference (namespaces are always explicit in the file)
- Configurable default namespace (root is the only implicit namespace)
- Changes to storage adapters, REST API, or `HippoClient` method signatures

## Decisions

### D1: Namespace declared in file, not inferred from path

**Decision**: The `namespace:` key in the schema file is the sole source of namespace assignment. Directory structure is not used.

**Rationale**: Path-based inference couples namespace identity to filesystem layout, making renames or restructuring a breaking change. Explicit declaration is more portable (S3-backed schemas, embedded schemas) and clearer in code review.

**Alternative considered**: Use directory names under `schemas/` as the namespace (e.g., `schemas/tissue/` → `tissue` namespace). Rejected because it constrains how teams organize files and breaks when files are moved.

---

### D2: Root namespace is the only implicit namespace

**Decision**: Files without a `namespace:` key contribute entities to a special root namespace. Root entities can be referenced as bare strings (`"Donor"`) or with the explicit prefix `"root.Donor"`. No other namespace is implicit.

**Rationale**: Backwards compatibility requires unqualified names to remain valid. Introducing a configurable default namespace would create ambiguity about which namespace bare names resolve to across different deployments. Fixing root as the only implicit namespace makes resolution deterministic.

**Alternative considered**: Allow a `default_namespace` config key. Rejected because it makes bare-name resolution non-portable across configs.

---

### D3: Namespace registry built at load time via `NamespaceRegistry`

**Decision**: Introduce a new `NamespaceRegistry` class (in `hippo/config/` or `hippo/core/`) that is populated by the `SchemaLoader` as it recurses the schema directory. The registry maps `(namespace, entity_name) → EntityConfig`. FQN resolution and cross-namespace reference validation are methods on this class.

**Rationale**: Separating registry concerns from the loader makes the graph-validation logic independently testable. The `SchemaConfig` object (used throughout the SDK) is populated from the registry after full resolution.

**Alternative considered**: Fold namespace resolution directly into `SchemaConfig`. Rejected because `SchemaConfig` is already used as a DTO downstream; mixing graph-validation logic into it increases coupling.

---

### D4: Dependencies inferred from references, validated in topological pass

**Decision**: No explicit `depends_on:` key. After loading all files, the registry performs a single topological sort over inferred edges (derived from `references.entity_type` FQNs). Circular dependencies raise `SchemaValidationError`. Unknown FQN references also raise `SchemaValidationError`.

**Rationale**: Explicit dependency declarations would be redundant (the references already encode the dependency) and error-prone (teams forget to update them). Inference is more robust and removes a maintenance burden.

**Alternative considered**: Require `depends_on:` per-file. Rejected for the reasons above.

---

### D5: Storage and transport layers require no changes

**Decision**: The SQLite adapter stores `entity_type` verbatim. `tissue.Sample` and `omics.Sample` are already distinct string values — no adapter changes needed. The REST API and `HippoClient` already accept `entity_type` as a string.

**Rationale**: FQNs are just strings from the perspective of everything below the SDK's schema layer. No migration of existing data is needed for deployments that don't adopt namespaces.

## Risks / Trade-offs

**[Risk] Entity type remapping deferred** → Teams that namespace-migrate a production entity (e.g., `Sample` → `tissue.Sample`) have no supported path today. Mitigation: Document the limitation prominently; block any such migration attempt until a remap command is implemented. See Open Questions.

**[Risk] Namespace registry built entirely in memory at load time** → Very large schema trees (thousands of entities) could slow startup. Mitigation: The registry is a simple dict; this is unlikely to matter in practice for foreseeable schema sizes. Reassess if schema counts grow beyond ~10k entities.

**[Risk] Silent merge of same-namespace files could mask conflicts** → Two files both declaring `namespace: tissue` will have their entity lists merged. If they both define an entity named `Sample`, the merge behavior (last-writer-wins vs. error) must be defined. Mitigation: Raise `SchemaValidationError` on duplicate `(namespace, entity_name)` pairs to fail loudly.

**[Risk] `root.Donor` and `Donor` must be strictly equivalent** → If any code path compares entity type strings without normalizing root-namespace FQNs, `"root.Donor" != "Donor"` bugs will appear. Mitigation: Canonicalize all FQNs to their unqualified form for root entities at registry ingestion time, so only `"Donor"` ever appears in `SchemaConfig` and storage.

## Migration Plan

1. Implement `NamespaceRegistry` and updated `SchemaLoader` behind a feature flag or in a non-breaking way (no existing paths change).
2. Update `hippo migrate` and `hippo validate --schema` to use the new namespace-aware loader.
3. Write migration guide for teams adopting namespaces: add `namespace:` key to new schema files, use FQNs in cross-references.
4. Existing single-file `schema.yaml` deployments require no action.
5. **No data migration required** for existing deployments.

**Rollback**: The namespace-aware loader is backwards compatible. Removing the `namespace:` key from all schema files restores prior behavior with no storage impact.

## Open Questions

### OQ1: Entity type remapping / namespace migration path

If a team needs to move `Sample` (root) to `tissue.Sample`, all stored rows and provenance records reference the old entity type. No migration tooling exists yet.

Options to explore before any production remapping attempt:
- `hippo migrate --remap Sample tissue.Sample` — explicit opt-in remap command
- Namespace aliasing — `tissue.Sample` as a read alias for `Sample` during a transition period
- Out-of-band data migration script with verification step

**This must be resolved before any production namespace adoption of existing entities.**

### OQ2: Canonical form for root-namespace entities in storage

Should `root.Donor` be stored as `"Donor"` or `"root.Donor"`? Decision: store as `"Donor"` (unqualified) to avoid a data migration for existing rows. The registry normalizes `root.*` to unqualified at load time. This should be documented as a firm invariant.
