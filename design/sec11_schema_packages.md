## 11. SchemaPackage Abstraction

**Document status:** Draft v0.1
**Depends on:** sec2_architecture.md, sec3_data_model.md, sec5_ingestion.md, sec9_linkml_redesign.md, sec10_recipes.md
**Feeds into:** appendix_b_implementation_guide.md

---

### 11.1 Overview & Motivation

#### 11.1.1 The Problem With a Flat ReferenceLoader

Hippo v0.1 ships `ReferenceLoader` as the single entry point for distributing versioned, pinnable schema fragments and the data that fills them. Two distinct concerns have accumulated in this one class:

1. **Versioned schema contribution.** Any reusable schema module — a controlled vocabulary, a data-model abstraction, a domain extension — needs versioning, `requires:` pinning, dependency ordering, and merge precedence. These are schema concerns, independent of data.
2. **External reference-data ingestion.** Biological reference databases (ontologies, gene catalogues, value sets) ship datasets that `load()` / `upgrade()` fetch, transform, and ingest. These are data concerns, where the source is external and reconstructible.

A pure-schema module that has no shipped data must write a no-op `load()` to satisfy the ABC. The `entity_types()` method has no meaning for such a module. This is a design smell: the abstraction is too narrow.

#### 11.1.2 The SchemaPackage Abstraction

**[PROPOSE, committed]** Abstract the reusable schema-contribution concern into a `SchemaPackage` genus. `ReferenceLoader` and the new first-party `DomainModule` become **sibling species** under it. Pure-schema modules use `SchemaPackage` directly with default no-op hooks.

This design:

- Eliminates no-op `load()` on schema-only packages.
- Gives domain-data migration (previously orphaned across §5–§6 of the migration design) a principled home as a peer of `ReferenceLoader`, sharing the same pinning, dependency graph, merge, and lifecycle orchestration.
- Preserves full back-compat: existing `ReferenceLoader` authors see no change.

---

### 11.2 Genus / Species Architecture

#### 11.2.1 Inheritance Diagram

```
           SchemaPackage (genus)
          /          \
    ReferenceLoader   DomainModule
    (external data)   (first-party, mutable data)

    Pure-schema modules: use SchemaPackage directly
    (default no-op hooks, no populates_types)
```

`ExternalData` and `MigratableData` are **capability protocols** (typing + orchestrator dispatch). Packages that carry data implement one or both protocols. The protocols carry behavior; the species hierarchy carries identity. This keeps `ReferenceLoader` and `DomainModule` as true siblings rather than forcing a deep inheritance chain.

```
    Protocol          Implemented by
    ─────────────     ──────────────────────────────
    ExternalData      ReferenceLoader
    MigratableData    DomainModule
```

#### 11.2.2 Genus: `SchemaPackage`

`SchemaPackage` is the pinnable schema contributor. Every package — regardless of species — implements this surface:

| Member | Kind | Description |
|---|---|---|
| `name` | property | Entry-point name; must equal `default_prefix` in `schema_fragment()` |
| `description` | property | Human-readable summary |
| `versions()` | method | Returns the set of versions this package ships |
| `schema_fragment()` | method | Returns the LinkML fragment; `default_prefix` = `name`; Hippo auto-injects `provided_by: <name>@<version>` on every introduced element |
| `depends_on()` | method | Returns `[(name, version_spec)]`; documents the dependency graph for orchestrator ordering and `requires:` pin generation |
| `validate(artifact)` | optional | Validates a caller-supplied artifact against this package's schema |
| `load_params_schema` | optional | Pydantic v2 model; CLI auto-renders `--flag` args from it and validates at input |
| `provision(client, version, params)` | hook | Install-time population; default no-op |
| `evolve(client, from_version, to_version, params)` | hook | Upgrade-time transition; default no-op |
| `deprovision(client, version)` | hook | Teardown; default no-op |

`provision` / `evolve` / `deprovision` default to no-op so a pure-schema package can be instantiated without overriding them.

`populates_types()` (formerly `entity_types()`) is a **species concern** — it declares which classes a package fills with data. Pure-schema packages omit it. `schema_fragment()` remains on the genus because every package contributes a fragment; `populates_types()` is separate because not every package populates data.

#### 11.2.3 Species: `ReferenceLoader`

`ReferenceLoader(SchemaPackage, ExternalData)` — external reference data. Method names are unchanged for author back-compat:

| Hook | Implementation |
|---|---|
| `provision` | Calls `load(client, version, params)` |
| `evolve` | Calls `upgrade(client, from_version, to_version, params)` (default re-ingests via `load(to_version)`) |
| `deprovision` | Prunes (soft-deletes) all rows carrying `provided_by: <name>@<version>`; safe because the source is external and reconstructible |

**[CONFORM]** `load(client, version, params=None) -> LoadResult` and `upgrade(client, from_version, to_version, params=None)` run inside `client.load_context(name, version)`; writes are recorded in `reference_write_log`. Every existing loader installs and operates unchanged.

#### 11.2.4 Species: `DomainModule`

`DomainModule(SchemaPackage, MigratableData)` — first-party, mutable data. Owns the deployment's operational domain records and migrates them in place:

| Hook | Implementation |
|---|---|
| `provision` | No-op by default (domain data arrives via `hippo ingest`, not at schema install time) |
| `evolve` | Runs the declared migration step(s) for the `(from_version, to_version)` range (§11.3) |
| `deprovision` | **Refuses by default** when it owns live domain data (§11.4.3); requires explicit `--force` and/or an export |

`DomainModule` is the principled home for semantic domain-data migration (previously orphaned as §5.2 / §6 of the migration design doc). DDL migration (`hippo migrate`) and `DomainModule.evolve` are complementary: `hippo migrate` handles additive DDL changes automatically; `DomainModule.evolve` handles semantic data transformations for major version changes.

#### 11.2.5 Entry-Point Groups

**[PROPOSE]** `hippo.schema_packages` is the new entry-point group. `hippo.reference_loaders` becomes a **subset / alias** — the discovery runtime queries both, deduplicates by name, and exposes `ReferenceLoader` instances from either group transparently. No existing loader needs to change its entry-point declaration.

---

### 11.3 Migration Chain

#### 11.3.1 Why a Chain

A `MigratableData` package must support multi-hop upgrades (e.g., `1.2.0 → 2.0.0` across intermediate versions `1.3.0`, `1.4.0`), where the breaking changes and their transforms live in the intermediate steps. Sorting version slugs is not the right path-finding mechanism — version slugs are opaque strings (see sec2 §2.14.C). Migration edges are explicit.

#### 11.3.2 Migration DAG

**[PROPOSE]** A `MigratableData` package declares **discrete migration steps**, each tagged `(from_version → to_version)` with its transform. These form a directed acyclic migration DAG:

```
    1.2.0 ──► 1.3.0 ──► 1.4.0 ──► 2.0.0
      │                             ▲
      └─────────── shortcut ────────┘
```

Properties:

- **All steps covering the package's supported range ship with the package at its current version.** The resolver never fetches old package code; the installed target carries its migration history back to a declared **floor** (like an Alembic `versions/` directory).
- **Shortcut edges** are optional. A package may declare a direct `1.2.0 → 2.0.0` edge that the path-finder prefers over the multi-step path when an efficient bulk transform is available.
- **Below-floor failure.** If the deployment's current version is older than the oldest migration step, the orchestrator fails loud: `"upgrade to ≥<floor> first via package <name>"`. This is the squashed-migration boundary; there is no silent fallback.
- Each step is small and independently testable; the resolver composes them. Authors write only one consecutive transition per step.

#### 11.3.3 Path Resolver

The resolver:

1. Reads the deployment's current version for the package from `hippo_meta.reference_versions` / registry.
2. Builds the path through the DAG from current to target, preferring shortcut edges.
3. Checks the floor; fails loud if the current version is below it.
4. Runs each step's `evolve` transform in order, one hop at a time.

Single-hop upgrades are a one-edge path through the same resolver — no special casing.

#### 11.3.4 Migration Step Authorship

Most major changes decompose into declarative moves (rename a field, set a default, widen a type) derivable from `hippo schema-diff <old> <new>`. Reserve hand-written transforms for genuinely semantic cases (splitting a field, re-rooting a value set, changing units). Each step writes supersession events, producing traceable lineage in the append-only provenance log.

---

### 11.4 `deprovision` Semantics

`deprovision` teardown removes the fragment and version record from the registry, then calls the package's hook to retire data.

#### 11.4.1 Default (Pure-Schema): No-Op

A `SchemaPackage` that contributes schema only has no data rows to clean up. Default `deprovision` is a no-op beyond registry removal.

#### 11.4.2 `ReferenceLoader`: Prune

`deprovision` prunes (soft-deletes) the loader's `provided_by`-stamped rows. This is safe because the source is external and reconstructible from the upstream data source.

#### 11.4.3 `DomainModule`: Refuse by Default

**`DomainModule.deprovision` refuses by default when the module owns live domain data.** Rationale: domain records are the lab's authoritative operational data. Silent soft-deletion on uninstall is a data loss event. The module must be deprovisioned explicitly:

- Pass `--force` to acknowledge the operation.
- Recommended: export the module's data first, then deprovision.

This asymmetry (`ReferenceLoader` prunes willingly, `DomainModule` refuses) reflects the difference in data ownership and reconstructibility.

#### 11.4.4 Dependents Guard

The orchestrator **refuses to deprovision any package that other installed packages declare in their `depends_on()`**. The error message names the dependent packages. This applies to all species.

---

### 11.5 Dependency-Ordered Lifecycle Orchestrator

**[PROPOSE]** A unified lifecycle orchestrator replaces the per-loader, unordered `hippo reference upgrade` path.

#### 11.5.1 Resolution

The orchestrator resolves the full `depends_on` graph across all installed packages once at the start of an operation, produces a topological sort, and dispatches lifecycle hooks across all affected packages in dependency order (base before dependents) for each version hop.

```
    resolve depends_on graph
          │
          ▼
    topological sort  →  [pkg_A, pkg_B, pkg_C, ...]
          │
          ▼
    for each hop in chain:
        for each pkg in topo order:
            pkg.evolve(client, from_v, to_v, params)
```

Per-hop dependency ordering means an extension's `evolve` always runs after its base has already reached that hop's shape. A coordinated multi-package upgrade sequences over intermediate **bundle** coordinates (§11.6.2); each hop = dependency-ordered per-package evolves.

#### 11.5.2 Staged Commit-or-Rollback

**[PROPOSE]** The orchestrator wraps the full chain in a staged transaction:

1. Run all `evolve` steps across hops and packages.
2. After each hop: validate against that hop's merged schema (error localization — catches errors early and names the offending hop).
3. After the final hop: validate against the final merged schema including all installed extensions **[CONFORM primitive; PROPOSE orchestration]** using `hippo ingest --validate-schema <merged-dir> --dry-run`.
4. Commit if all validations pass; roll back everything otherwise.

The end-to-end gate is the real backstop. Per-hop intermediate validation is an ergonomic aid.

---

### 11.6 Coherence Tools

#### 11.6.1 Exposure Report Tool

**[PROPOSE]** The exposure-report tool answers: *given a proposed base-package migration, which elements of an installed extension are in the migration's write-set?*

Inputs: the base migration's structural delta (from `hippo schema-diff <old_schema> <new_schema>`) and the extension's referenced elements (`is_a`, `slot_usage`, and added-slot dependencies).

Output: the intersection — elements the base migration writes that the extension references. An empty intersection means the base migration is safe to apply without an extension step. A non-empty intersection means the extension must supply a complementary `evolve` step covering those elements.

Purpose: warn extension authors *before* migration about the footprint of a base upgrade, before the end-to-end gate runs.

#### 11.6.2 `brainbank-bundle` — Illustrative Proving Case

**[PROPOSE]** A `brainbank-bundle` meta-coordinate is the illustrative reference implementation of the bundle concept: a single manifest that pins one coherent `(loader → version + ontology snapshot)` set for the brain bank deployment.

The bundle is CI-validated: the `requires:` block in the user schema is generated from the bundle manifest, not hand-maintained. This ensures the deployment's pinned versions always correspond to a known-coherent combination.

Hippo has no bundle concept today; `brainbank-bundle` is the first instantiation. The bundle pattern is domain-neutral: any deployment with multiple inter-dependent packages benefits from one.

#### 11.6.3 CI Merged-Closure Integrity Check

**[PROPOSE]** A CI check that validates the **fully merged schema closure** — the result of merging all `requires:`-pinned packages into the user schema — against a reference snapshot.

Purpose: cross-package foreign keys are not validated at runtime in v1 (only a warning; see §1 and sec2 §2.14.H). The CI check stands in for that missing runtime enforcement: if the merged closure is structurally incoherent (unresolvable FK, missing base class, duplicate slot name), CI fails before the change ships.

The check runs `hippo validate --schema <merged_dir>` against the merged schema YAML produced by the registry. It does not require a live deployment.

---

### 11.7 [CONFORM] vs. [PROPOSE] Summary

#### 11.7.1 Use As-Is — [CONFORM]

These hippo capabilities underpin the SchemaPackage abstraction but require no new implementation:

- `ReferenceLoader` ABC: `load()`, `upgrade()`, `validate()`, `cached_fetch()`, `--prune-old`, `"test"` fixture convention, `schema_fragment()` with `default_prefix = name`, `provided_by` auto-injection, entry-point discovery via `hippo.reference_loaders`.
- `requires:` version-pin gate + refuse-on-mismatch at schema load.
- Three-layer merge precedence (user schema > reference loaders > `hippo_core`/`hippo_ext`).
- `hippo migrate` (additive DDL reconciliation).
- `hippo schema-diff <a> <b>` (structural delta / migration footprint).
- `hippo ingest --validate-schema <dir> --dry-run` and `hippo validate --data` (end-to-end validation gate primitive).
- `loader_depends_on` annotation (documentation-only; emits a warning on missing dependency; runtime does not enforce ordering).
- `hippo_meta.reference_versions` (installed version registry).
- `reference_write_log` and `client.load_context()` (write-log plumbing for `--prune-old`).

#### 11.7.2 Build — [PROPOSE]

| Deliverable | Sprint |
|---|---|
| `SchemaPackage` genus ABC + `ExternalData`/`MigratableData` protocols; `ReferenceLoader` re-parented as species; `hippo.schema_packages` entry-point group with `hippo.reference_loaders` as alias | S0 |
| `DomainModule` species + single-hop `evolve`; supersession + provenance; staged dry-run gate | S2 |
| Migration-chain resolver (DAG, shortcut edges, floor, below-floor fail-loud); multi-hop `evolve`; `deprovision` with asymmetry + dependents guard | S3 |
| Dependency-ordered lifecycle orchestrator; staged commit-or-rollback wrapping end-to-end gate (incl. extensions); `brainbank-bundle` + generated `requires:`; exposure-report tool; CI merged-closure integrity check | S4 |

---

### 11.8 Open / [VERIFY] Items

| Item | What to verify | Sprint | Status |
|---|---|---|---|
| Whole-`evolve`/`upgrade()` multi-entity transaction atomicity | Does `client.load_context()` / the per-write transaction guarantee rollback across multiple entity types if `evolve`/`upgrade()` fails mid-way? Is there a full-upgrade rollback? | S3 | **Resolved (§11.8.1)** |
| Runtime `loader_depends_on` ordering | Does any runtime path (e.g., `hippo reference upgrade`) order loader invocations by `loader_depends_on`? Or is the annotation strictly documentation today? | S3/S4 | Open (§11.8.2) |

#### 11.8.1 Multi-entity transaction atomicity — RESOLVED (S3)

**Finding: there is no whole-`evolve` / whole-`upgrade()` multi-entity transaction. Verified against the hippo source.**

The transaction boundary is **per single write**, not per upgrade:

- `HippoClient.put()` → `IngestionService._put_with_sqlite()` → `SQLiteAdapter.create()` / `update_data()`, each of which wraps its body in exactly one `with self._storage._transaction() as conn:` and commits on exit.
- `HippoClient.supersede_entity()` → `ProvenanceService.supersede_entity()`, likewise its own single `_storage._transaction()`.
- `client.load_context()` only threads the `(loader_name, version)` write-log tag so the `reference_write_log` row insert shares **that one** entity write's transaction (so a committed entity row always has a matching log row, and a mid-write fault rolls back *that* write). It does **not** open an enclosing transaction across the whole load/upgrade.

Consequence: a fault *between* committed writes — e.g. `evolve` raises on the 3rd `put`, or `supersede_entity` fails after some `put`s committed, or any hop of a multi-hop chain fails after earlier hops committed — leaves **partial state with no automatic rollback** across the operation. `--prune-old` does not corrupt the prior version on failure (it is gated behind a clean `LoadResult`, so the prune is simply skipped), but the *new*-version partial writes persist.

Mitigation already shipped (S2/S3): `DomainModule.evolve` runs a **pre-commit staged dry-run gate** (`_run_gate`) that validates the transform output against the merged schema *before any write*, so the most common failure mode — schema-invalid output — never reaches the commit loop and nothing is written. The gate cannot, however, undo a runtime fault that occurs *during* the commit loop.

Designed home for true atomicity: the **S4 orchestrator's staged commit-or-rollback** (§11.5.2), which wraps the full chain (all hops, all packages, extensions included) in one staged transaction and rolls everything back if the end-to-end gate fails. End-to-end multi-entity rollback is explicitly deferred there; S3 documents the limitation rather than papering over it.

#### 11.8.2 Runtime `loader_depends_on` ordering — partially addressed (S3), full ordering S4

As of S3, `depends_on()` has its **first runtime consumer**: the `deprovision` *dependents guard* (§11.4.4) refuses to tear down a package that any installed package still depends on. Dependency-*ordered* lifecycle dispatch on the install/upgrade path (base before dependents, per hop) remains the S4 orchestrator's job (§11.5.1); today `hippo reference upgrade` still operates per-package without a topological sort.
