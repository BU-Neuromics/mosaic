# sec9 Handoff — Recipes v1

**Date:** 2026-05-27
**Target completion:** ~2 weeks of focused engineering
**Tracking issue:** _to be filed_

---

## TL;DR

Add a **Recipe** system to Hippo: a declarative, content-addressed, version-pinned bundle that packages a LinkML schema fragment so it can be shared between deployments. A recipe is a manifest + a schema YAML, distributed as either a directory or a tarball, resolved from `file:` or `https:` URIs, and verified by sha256 digest at install time. Recipes carry a `parent` lineage pointer and a `requires:` list so derivative deployments preserve attribution and are reproducible from manifest alone.

This generalises today's Reference Loader pattern: the Reference Loader stays unchanged in v1, but the design positions it as a future "recipe producer" — a Python-distributed loader that runs imperative ingestion and may, in a later phase, emit a recipe as its install artifact.

**Implementation must not begin until `design/sec10_recipes.md` is authored and merged** (Phase 1 below). That section, not this handoff, is the authoritative design spec — this handoff is the implementation directive. Where the two disagree, fix `sec10` and update this handoff to match.

V1 ships **schema only**. No data sidecar. No federation / HTTP endpoint. No overlay / harmonize import mode. No 3-way merge or `rebase`. No signing. Schema-level "overrides" are achieved via native LinkML inheritance (`is_a:` + `slot_usage:` + `attributes:`) on the user side, not via in-place mutation of upstream classes.

---

## Read first

Read these in order before starting:

1. **`hippo/src/hippo/core/schema_manager.py`** — owner of all LinkML schema merging, prefix collision checks, and `provided_by` annotation injection. RecipeService composes this; do **not** reimplement schema-merge logic inside RecipeService.
2. **`hippo/src/hippo/core/ingestion_service.py`**, **`provenance_service.py`**, **`query_service.py`** — the service-facade pattern RecipeService must follow. Each is a single class instantiated in `HippoClient.__init__` and exposed through thin delegating wrappers.
3. **`hippo/src/hippo/core/client.py`** — `HippoClient` composition point. The diff to this file in v1 is one new `self._recipe_service = RecipeService(...)` line plus a small set of delegating wrappers.
4. **`hippo/src/hippo/core/loaders/reference.py`** — the existing Reference Loader install path. RecipeService reuses its content-addressable cache pattern and its `hippo_meta.reference_versions` registry shape. Do not change this file in v1.
5. **`hippo/src/hippo/core/meta.py`** — `hippo_meta` registry helper. The new `installed_recipes` key lives here.
6. **`hippo/src/hippo/schemas/hippo_core.yaml`** — sibling location for the new `recipe_manifest.yaml` schema this work introduces.
7. **`hippo/design/sec9_linkml_redesign.md` §9.5–§9.7** — the LinkML-native invariants every new component must preserve (closed-schema validation, schema-driven, annotation discipline).

---

## Scope

### In scope

| Step | Description |
|---|---|
| 1 | Add `src/hippo/schemas/recipe_manifest.yaml` — LinkML schema defining `RecipeManifest` and `RecipeRef`. |
| 2 | New module `src/hippo/core/recipe_service.py` exposing `RecipeService`. Optional small subpackage `src/hippo/core/recipe/` for dataclasses (`ImportPlan`, `ImportResult`, `RecipeReport`, `RecipeDiff`, `InstalledRecipe`) if they grow past ~80 lines inline. |
| 3 | Two resolvers behind a `RecipeResolver` interface: `FileResolver` (handles `file:` URIs and bare paths) and `HttpsResolver` (handles `https:` URIs). No other schemes in v1. |
| 4 | Content-addressable cache at `~/.hippo/recipe-cache/<sha256>/` for fetched recipes. Cache key is the digest; cache hit skips network. |
| 5 | Bootstrap import — installs a recipe whose declared `name`/`default_prefix` does not collide with any currently installed prefix. No merge / overlay in v1. |
| 6 | `installed_recipes` section in `hippo_meta`, mirroring the shape of `reference_versions`. |
| 7 | CLI commands: `hippo recipe list | inspect | import | export | extend | diff | export-lockfile | install-from-lockfile`. |
| 8 | `HippoClient` thin delegators for each `RecipeService` public method. |
| 9 | `provided_by: recipe.<id>@<version>` injection on all classes/slots imported via a recipe — applied by `SchemaManager` at the merge call, sourced from the manifest's identity. |
| 10 | One new provenance event kind `recipe_imported`, emitted in the same transaction as the schema merge. |

### Out of scope (deferred to v2 or later)

- **Federation / HTTP `/recipe` endpoint.** No server-side surface.
- **Overlay / harmonize import modes.** Only bootstrap install in v1.
- **Cross-namespace schema overrides.** Users override by subclassing upstream classes locally via LinkML inheritance. In-place mutation of an upstream class is explicitly disallowed in v1.
- **`recipe rebase` / 3-way schema merge.**
- **Data sidecar / seed rows.** LinkML enums (`permissible_values:`) cover small controlled vocabularies inside `schema.yaml`. Bulk reference data continues to ship via Reference Loaders declared in `requires.reference_loaders`.
- **Signing / authorship trust.** v1 verifies bytes (digest), not authorship. v2 may layer on sigstore/minisign.
- **Recipe uninstall.** Consistent with the no-hard-deletes principle. Workaround: rebuild instance from a lockfile that omits the unwanted entry. State this in the user docs.
- **Discovery / search / registry.** No `hippo recipe search`. Users find recipes the way they find Python packages (READMEs, lab wikis, DOIs).
- **Refactoring Reference Loader internals to use RecipeService.** Keep the loader on its existing code path. Convergence happens in a later phase.
- **`git:` / `oci:` URI schemes.** `file:` + `https:` only.

---

## Architecture invariants

These must remain true after every PR in this work. The implementing agent should reject its own changes that violate any of them.

1. **`SchemaManager` owns schema merging.** `RecipeService` never touches LinkML `SchemaView` directly to merge — it calls `SchemaManager` and lets that class enforce prefix collision, closed-schema validation, and `provided_by` injection.
2. **All schema writes from a recipe import flow through `SchemaManager.merge_fragment(...)`** (or whichever exact method the implementer chooses to add/use) so future invariants added there apply to recipes for free.
3. **Provenance is unconditional.** Every successful recipe import writes exactly one `recipe_imported` provenance entry in the same transaction as the schema merge. Failed imports leave no state change in either store.
4. **Digest is the source of truth.** When a `RecipeRef` declares a `digest`, the install path verifies it against the freshly fetched bytes and aborts on mismatch with `RecipeDigestMismatchError`. When no digest is declared (only legal for `file:` sources in v1), the install path computes one and records it in `installed_recipes`.
5. **No implicit lineage.** Editing the live schema after a recipe import does not retroactively attach those edits to the recipe. Lineage is created only by `hippo recipe extend` and propagated only by an explicit subsequent `import` of the extended recipe.
6. **No in-place override of upstream classes.** The merge layer rejects a recipe whose schema modifies a class/slot whose `provided_by` annotation names a different recipe or loader. Users override by subclassing (`is_a:`). The implementing agent must add a check for this in the SchemaManager seam.
7. **`provided_by` is set, not inferred.** `recipe.<id>@<version>` is injected by the merge layer. `loader.<name>@<version>` continues to be injected by the Reference Loader path. Annotations a recipe author hand-writes for `provided_by` are overwritten — the manifest identity wins.

---

## Phased work plan

Four phases, each PR-sized at the boundaries. Phases must land in order. Phase 1 produces the authoritative design spec; Phases 2–4 are implementation and may not begin until Phase 1 has merged.

### Phase 1: Author the design spec — COMPLETE

**Goal:** produce `design/sec10_recipes.md`, the durable design section for the recipe subsystem. From this phase onward, `sec10` is the authoritative spec; this handoff is reduced to "how to execute it."

**Required structure** — follow the convention of `sec1`–`sec9`: numbered subsections, tables for structured data, ASCII diagrams for architecture. Suggested subsection map (adjust as you see fit, but cover all the material):

| Subsection | Content |
|---|---|
| 10.1 Overview & Motivation | What a recipe is; how it generalises Reference Loaders; what problem reproducibility-of-deployments solves. |
| 10.2 Architecture | `RecipeService` as a service facade composed with `SchemaManager` and `ProvenanceService`. Diagram of the install pipeline (source → resolver → cache → manifest validate → dep resolve → schema merge → provenance write). |
| 10.3 Data Model | `RecipeManifest`, `RecipeRef`, `installed_recipes` registry shape, lineage via `parent`. |
| 10.4 Install Semantics | Resolvers (`file:`, `https:`), content-addressable cache, digest algorithm, bottom-up dependency resolution, cycle detection, atomicity. |
| 10.5 Export Semantics | Selectivity by `provided_by`, parent/requires inference, what is and is not packaged. |
| 10.6 Reproducibility Model | Digest as source of truth, lockfile as portable deployment manifest, round-trip guarantee, documented limits (URL availability, no signing in v1). |
| 10.7 Override & Extension Model | LinkML-native inheritance for overrides; explicit rejection of in-place override of upstream classes; `extend` workflow. |
| 10.8 Error Model & Provenance | Error hierarchy and the `recipe_imported` provenance event. |
| 10.9 Out of Scope (v1) | Federation, overlay/harmonize, data sidecar, signing, uninstall — each with a one-sentence rationale and pointer to the v2 surface. |

**Source material:** the rest of this handoff is the source. Restructure for readability rather than copying verbatim. Resolve any drafting decisions still ambiguous in this handoff — including the three open questions at the bottom — inside `sec10`, and update this handoff to match before closing the PR.

**Also in this phase:** add a row to `design/INDEX.md` for `sec10_recipes.md`. Status: `Draft v0.1`.

**Acceptance gate:** Phase 2 may not start until the `sec10` PR is merged. The implementation phases reference `sec10` by section number, not this handoff, in code comments and commit messages.

### Phase 2: Schema-level groundwork

**Goal:** the `RecipeManifest` LinkML schema, the dataclasses, the empty service shell. No CLI, no fetch, no install behavior.

Suggested PR boundaries — one PR per:

1. Add `src/hippo/schemas/recipe_manifest.yaml` (`RecipeManifest` + `RecipeRef`). Ship a unit test that loads it via `SchemaView` and validates a hand-written example manifest.
2. Add `core/recipe/` dataclasses (`InstalledRecipe`, `RecipeReport`, `RecipeDiff`, `ImportPlan`, `ImportResult`) — Python types only, no behavior.
3. Add `core/recipe_service.py` with `RecipeService(__init__, list_installed)` and the new `installed_recipes` accessor on `hippo_meta`. Wire one delegator in `HippoClient`: `client.recipe_list()`.
4. Extend `SchemaManager` with the no-in-place-override check (invariant 6). Tests: a recipe trying to redefine a class previously installed by another recipe is rejected; a recipe adding a subclass (`is_a:` upstream) is accepted.

### Phase 3: Install path

**Goal:** end-to-end bootstrap install from a local directory and from an https URL. CLI surface partially live.

5. `RecipeResolver` interface + `FileResolver`. Implement `RecipeService.inspect(source)` against it. CLI: `hippo recipe inspect`.
6. `HttpsResolver` + content-addressable cache (`~/.hippo/recipe-cache/<sha256>/`). Mandatory digest verification for `https:` sources; computed-and-recorded for `file:` sources. New errors: `RecipeFetchError`, `RecipeDigestMismatchError`.
7. `RecipeService.import_(source, dry_run=False)` for the bootstrap-only case: parse manifest → resolve & install dependencies (parent + `requires.recipes`) bottom-up → call `SchemaManager.merge_fragment(...)` → write `installed_recipes` entry → emit `recipe_imported` provenance entry. All inside a single storage transaction. CLI: `hippo recipe import`.
8. `RecipeService.export(scope="schema")` and `hippo recipe export`. Export semantics defined under "Export rules" below.

### Phase 4: Authoring and reproducibility ergonomics

**Goal:** the rest of the CLI and the lockfile flow.

9. `RecipeService.extend(installed_id, out_dir)` → scaffolds a directory with a manifest carrying a populated `parent: RecipeRef` (resolved from `installed_recipes`) and an empty `schema.yaml`. CLI: `hippo recipe extend`.
10. `RecipeService.diff(a, b)` → structural diff over the two manifests' schemas (classes added/removed/changed, slots added/removed/changed). CLI: `hippo recipe diff`.
11. `RecipeService.export_lockfile(out)` → dumps `installed_recipes` as a portable YAML document (`recipe.lock.yaml`). `RecipeService.install_from_lockfile(lockfile)` → iterates entries in dependency order, fetching each via its `source`, verifying each `digest`, and installing. CLI: `hippo recipe export-lockfile`, `hippo recipe install-from-lockfile`.

---

## Recipe artifact specification

### Layout

```
my-recipe/                # directory form
├── recipe.yaml           # manifest, validated against recipe_manifest.yaml
└── schema.yaml           # LinkML schema fragment
```

Tarball form: `tar -czf my-recipe.tar.gz my-recipe/` — the contained directory MUST be the recipe root, not the tarball itself. Inspect/import accepts either form; the resolver normalises tarballs by extracting into a temp directory and operating on the directory form.

### Manifest fields

Defined in `src/hippo/schemas/recipe_manifest.yaml`. Required vs optional listed; full LinkML schema is the source of truth.

| Field | Required | Notes |
|---|---|---|
| `id` | yes | Reverse-DNS style stable identifier, e.g. `org.broad.scrnaseq`. |
| `name` | yes | Short, file-system safe. Becomes the LinkML `default_prefix` for the schema fragment. |
| `version` | yes | Opaque slug. SemVer recommended in user docs but not enforced by Hippo. |
| `description` | no | Human-readable, one paragraph. |
| `author` | no | Sub-object: `name`, `email`, `organization`. |
| `license` | no | SPDX identifier. |
| `created_at` | yes | ISO 8601 UTC instant. |
| `hippo_version` | yes | PEP 440 version specifier (e.g. `">=0.3,<0.5"`). Parse with `packaging.specifiers.SpecifierSet`; introduce that dep if not already present. |
| `source` | no | Author-declared canonical origin URI (e.g. a Zenodo DOI URL). Metadata only — Hippo never fetches from it. Distinct from per-RecipeRef and installed-recipe `source` fields; the three may legitimately disagree. |
| `parent` | no | `RecipeRef`. Present on extended recipes. Auto-resolved at install (see "Parent vs requires" below). |
| `requires.recipes` | no | List of `RecipeRef`. |
| `requires.reference_loaders` | no | List of pin strings `name==version`. Existing Reference Loader convention. |

### RecipeRef shape

A single LinkML class reused for `parent`, `requires.recipes[i]`, and entries in `installed_recipes`:

| Field | Required | Notes |
|---|---|---|
| `id` | yes | Matches `RecipeManifest.id` of the referenced recipe. |
| `version` | yes | Matches `RecipeManifest.version`. |
| `source` | yes (in v1) | `file:` URI, bare path, or `https:` URI. Relative paths in a manifest resolve against the **importing recipe's directory**. Relative paths in a lockfile resolve against the **lockfile's directory**. |
| `digest` | required when `source` is `https:`; optional but recorded when `source` is `file:` | sha256 over the canonical content hash (algorithm below). |

`installed_recipes` entries extend `RecipeRef` with `installed_at` (ISO 8601 UTC) and may additionally carry the original manifest's `parent` field as an embedded sub-object for audit.

### Digest algorithm

The digest is computed over the recipe's **canonical content hash**, not over the tarball bytes (which are repack-sensitive). Algorithm:

1. Enumerate all files in the recipe directory recursively, relative to the recipe root.
2. Sort the file list lexicographically by relative path.
3. Build a buffer by concatenating, for each file in order: `<relative-path-as-utf8>\n<lowercase-hex-sha256-of-file-bytes>\n`.
4. The recipe digest is `sha256(buffer)`, lowercase hex.

This algorithm yields the same digest whether the recipe is shipped as a directory or a tarball, and is stable across repacking. No file is excluded — the recipe directory IS the recipe. Document this in the user-facing CLI reference.

Reference implementation must live in `core/recipe/digest.py` and be a single ~20-line function. `hippo recipe inspect` prints the computed digest for authoring convenience.

### Parent vs requires

`parent` is **auto-resolved** as a dependency at install time. A child manifest does NOT need to also list its parent in `requires.recipes`. The parent pointer is itself a typed dependency.

`requires.recipes` lists all OTHER recipe dependencies (siblings or peers, not ancestors). The merge into the live schema is bottom-up: parent → requires → self.

Cycle detection is mandatory across both `parent` and `requires.recipes`. Implementation: keep a visiting set during the resolution recursion; emit `RecipeLineageCycleError` on revisit.

### Export rules

`hippo recipe export` packages only the **locally-authored** content of the live schema — classes and slots whose `provided_by` annotation is absent or does not start with `recipe.` or `loader.`. Upstream content from imported recipes and Reference Loaders is excluded. This prevents accidental re-distribution of upstream content, protects attribution, and lets the export be installed cleanly on a peer instance that already has the same upstream recipes installed.

The resulting manifest's `parent` is left empty by default. If the user wants to declare lineage, they pass `--parent <installed-id>` and Hippo populates `parent` from the matching `installed_recipes` entry. The `requires.recipes` list is populated automatically from the set of installed recipes whose content is referenced by `is_a:` or slot ranges in the exported schema.

---

## Reproducibility model

Two primitives:

**Content addressing.** A recipe is identified by its sha256 canonical-content-hash digest. URIs are resolvers — they tell Hippo where to fetch the bytes. The contract: declared digest → verify; no declared digest (legal only for `file:`) → compute and record. Tag drift, link rot of mutable URLs, MITM substitution are all caught loudly.

**Lockfile = `installed_recipes`.** The `hippo_meta.installed_recipes` registry already carries `{id, version, source, digest, installed_at, parent?}` per installed recipe. `hippo recipe export-lockfile` dumps that registry as a portable YAML; `hippo recipe install-from-lockfile` re-fetches each entry by its `source`, verifies each `digest`, and installs in dependency order. Together these provide a full reproducibility round-trip — a deployment can be re-created on a peer instance from a single file, provided each entry's `source` URI is still resolvable.

V1 reproducibility limits, documented for users:

- URL availability is out of Hippo's control. Encourage DOI-minted releases (Zenodo, etc.) for canonical recipes.
- Digest verifies integrity but not authorship. Signing is v2.
- Mutable tags (e.g. `latest.tar.gz`) are technically allowed but self-defeating with the required digest. Spec discourages but does not forbid.

---

## CLI surface (v1)

```
hippo recipe list                              # installed recipes
hippo recipe inspect <path-or-uri>             # parse + validate, no DB writes; prints digest
hippo recipe import <path-or-uri> [--dry-run]  # bootstrap-only install
hippo recipe export [--out PATH] [--parent <installed-id>]
hippo recipe extend <installed-id> --out PATH  # scaffold derivative directory
hippo recipe diff <a> <b>                      # structural diff (paths or URIs)
hippo recipe export-lockfile [--out PATH]      # dump installed_recipes as portable YAML
hippo recipe install-from-lockfile <file>      # re-fetch + verify + install
```

CLI lives in the existing CLI module structure; one new `hippo/cli/recipe.py` mirroring how other subcommands are organised. CLI calls `HippoClient` delegators; never reaches into `RecipeService` directly.

---

## SDK surface

```python
# src/hippo/core/recipe_service.py
class RecipeService:
    """Manages recipe export, inspection, lineage, and bootstrap import.

    This facade owns all recipe-related logic. Delegates schema merging to
    SchemaManager and provenance writes to ProvenanceService. Reference Loader
    installs do not go through this service in v1.
    """

    def __init__(
        self,
        storage: SQLiteAdapter,
        schema_manager: SchemaManager,
        provenance_service: ProvenanceService,
        cache_dir: Path | None = None,
        resolvers: Sequence[RecipeResolver] | None = None,
    ) -> None: ...

    def list_installed(self) -> list[InstalledRecipe]: ...
    def inspect(self, source: str | Path) -> RecipeReport: ...
    def import_(self, source: str | Path, *, dry_run: bool = False) -> ImportResult: ...
    def export(self, *, scope: str = "schema", parent: str | None = None) -> Recipe: ...
    def extend(self, installed_id: str, out_dir: Path) -> Path: ...
    def diff(self, a: str | Path, b: str | Path) -> RecipeDiff: ...
    def export_lockfile(self, out: Path) -> None: ...
    def install_from_lockfile(self, lockfile: Path) -> list[ImportResult]: ...
```

`HippoClient` delegators are thin wrappers, one per public method, named `recipe_<verb>`.

---

## Error hierarchy

Define under `core/exceptions.py` (existing module). All inherit from the existing base error.

| Error | Cause |
|---|---|
| `RecipeManifestError` | Manifest fails LinkML validation against `recipe_manifest.yaml`. |
| `RecipePrefixCollisionError` | Incoming recipe's `name`/`default_prefix` collides with an installed prefix from any source (recipe, loader, hand-authored). |
| `RecipeRequiresUnsatisfiedError` | A declared `requires.recipes` or `requires.reference_loaders` dep cannot be resolved. Message must include the unresolved `RecipeRef.source` URI. |
| `RecipeVersionIncompatibleError` | `hippo_version` SpecifierSet excludes the running Hippo version. |
| `RecipeLineageCycleError` | Parent / requires graph contains a cycle. |
| `RecipeSchemaError` | Embedded `schema.yaml` fails LinkML validation, or `SchemaManager.merge_fragment` rejects (including the no-in-place-override check). |
| `RecipeFetchError` | Resolver could not retrieve the artifact (404, network error, unreadable tarball). |
| `RecipeDigestMismatchError` | Fetched bytes' canonical-content-hash digest does not match the digest declared in the `RecipeRef`. |

Every error must include the recipe `id` + `version` and the failing `RecipeRef.source` in its message when those are known.

---

## Provenance entries

One new event kind: `recipe_imported`. Schema lives in `hippo_core.yaml` alongside existing provenance event kinds. Required payload:

| Field | Notes |
|---|---|
| `recipe_id` | |
| `recipe_version` | |
| `recipe_digest` | The verified-or-computed sha256. |
| `recipe_source` | The exact URI Hippo fetched from (post-resolution). |
| `parent` | `RecipeRef` or null. |
| `classes_added` | List of qualified class names introduced by this import. |
| `slots_added` | List of qualified slot names introduced by this import. |

Emit exactly one event per top-level import. Bottom-up dependency installs each emit their own event in the same transaction.

---

## Tests

Place under `tests/recipe/`. Minimum surface:

- **Manifest validation:** valid manifest loads; each required field missing produces `RecipeManifestError`.
- **Digest stability:** dir-form and tarball-form of the same recipe produce identical digests; reordering files in the tarball does not change the digest.
- **Resolvers:** `FileResolver` resolves `file:` URIs, bare absolute paths, and bare relative paths (relative to importing recipe). `HttpsResolver` fetches and caches; cache hit on second fetch.
- **Bootstrap install:** dry-run leaves no state change; real install creates `installed_recipes` entry and `recipe_imported` provenance entry; failure mid-merge rolls back both.
- **Digest mismatch:** modifying bytes after declaring digest produces `RecipeDigestMismatchError`.
- **Prefix collision:** importing a recipe whose `name` matches an installed prefix fails atomically.
- **No in-place override:** a recipe redefining an existing class fails; a recipe adding `is_a: upstream:Class` succeeds.
- **Lineage cycle:** A requires B requires A produces `RecipeLineageCycleError`.
- **Lockfile round-trip:** export, wipe instance, install-from-lockfile reproduces identical `installed_recipes` digests.
- **Export selectivity:** instance with one imported recipe + local additions exports only the local additions.

---

## Open questions — RESOLVED in sec10

These were flagged for resolution before Phase 2 begins. All three are resolved in `design/sec10_recipes.md §10.12`. Summary:

1. **`requires.reference_loaders` resolution** — **Precondition only.** v1 does NOT install RLs as a side effect of recipe import. Hippo checks that each pinned RL is installed at the declared version; failure raises `RecipeRequiresUnsatisfiedError`. See sec10 §10.4.5.
2. **Lockfile schema version** — **Yes.** `recipe.lock.yaml` carries `lockfile_version: 1` at the top level for forward-compatible parsing. See sec10 §10.6.2.
3. **Cache-dir override** — **Yes.** `HIPPO_RECIPE_CACHE` env var overrides `~/.hippo/recipe-cache/`, parallel to existing cache conventions. See sec10 §10.4.2 and §10.4.6.

---

## Definition of done

- **`design/sec10_recipes.md` authored and merged** as the authoritative design spec (Phase 1). `design/INDEX.md` carries a row for it.
- All ten "in scope" steps merged across Phases 2–4.
- All architecture invariants hold under the new test suite.
- `hippo recipe import` + `hippo recipe export-lockfile` + `hippo recipe install-from-lockfile` round-trip on a real instance with at least one imported recipe and one local extension.
- User documentation pages added under `docs/`: `writing-a-recipe.md`, `installing-recipes.md`, `recipe-reference.md` (manifest field reference). The Reference Loader docs gain a single paragraph cross-link to recipes.
- Any drift between `sec10` and this handoff resolved in favour of `sec10`; this handoff updated accordingly before the final implementation PR merges.
