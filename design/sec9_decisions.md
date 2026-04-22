# sec9 Autonomous Drafting — Decisions for Review

The user requested that sec9 (sections 9.7–9.13) be drafted without real-time feedback. This file captures every opinionated call made during that drafting pass. Each entry describes the decision point, the alternatives considered, the choice made, the reasoning, and how to revert if the call is wrong.

Review this file before sec9 is considered approved. If any decision is unwelcome, the rollback column indicates the blast radius.

---

## 9.7 Computed Temporal Fields

### Decision 9.7.A — Computation strategy: on-the-fly aggregation, no materialization by default [CONFIRMED 2026-04-18]

- **Alternatives:** (1) read-time aggregation only; (2) materialized view maintained by adapter; (3) hybrid (aggregation with opt-in materialization per-adapter).
- **Chosen:** (1) read-time aggregation; stateless. Optimization strategies are deferred to future work / add-ons.
- **Why:** Keeps SDK contract uniform across adapters; no adapter is forced to implement a materialization strategy; performance is acceptable at Hippo's scale given the required indexes.
- **Revert:** Can move to (2) or (3) adapter-by-adapter without changing SDK surface.

### Decision 9.7.B — Fields computed: `created_at`, `updated_at`, `schema_version`, plus `created_by` and `updated_by`

- **Alternatives:** Minimal set (timestamps + version only); full set including `_by` actor references.
- **Chosen:** Full set. `created_by` and `updated_by` pull from the corresponding provenance record's `actor_id`.
- **Why:** Actor attribution is a near-universal audit query; computing it from provenance is cheap in the same aggregation; adding the fields now avoids a future additive-but-visible change.
- **Revert:** Drop the two `_by` fields; their absence is additive-compatible (they'd be absent from reads).

### Decision 9.7.C — Always included on entity reads

- **Alternatives:** Opt-in via a `with_temporal=True` flag; always included.
- **Chosen:** Always included.
- **Why:** Absent temporal fields would surprise agent implementers; the aggregation is bounded (2 point-in-time lookups per entity with the declared index); conditional inclusion complicates the SDK contract with no compelling use case.
- **Revert:** Move to opt-in by adding a flag to the reader; low blast radius.

### Decision 9.7.D — Degenerate case (no provenance records): raise loudly, refuse to return the entity [REVISED 2026-04-18]

- **Alternatives:** Raise an integrity error; return null; materialize synthetic provenance.
- **Original choice:** Return null (soft degradation).
- **Revised choice:** Raise `ProvenanceIntegrityError`; refuse to return the entity. Writes that cannot emit a valid provenance record fail atomically — the entity change rolls back.
- **Why (revised):** Provenance integrity is the audit guarantee the system exists to provide. Silent degradation on a provenance inconsistency would compromise every audit, compliance, and debugging use case. Transactional write atomicity prevents the inconsistent state from arising under normal operation; loud read-time failure surfaces any that do arise (from bugs or corrupted adapters) immediately instead of masking them. Sec9 adds `Provenance integrity is transactional and loud` as a first-class principle in 9.2.
- **Revert:** Change to null-return in 9.7's "Degenerate cases" paragraph; drop the 9.2 principle; weaken 9.6's atomicity clause. High blast radius — this is a governing invariant.

---

## 9.4 `hippo_ext` Extension Vocabulary

### Decision 9.4.A — Scrub `hippo_summary_view` and auto-emitted summary views entirely [NEW 2026-04-19]

- **Finding (from the 2026-04-18 autonomous session):** sec9 §9.4 listed `hippo_summary_view` as a class-level annotation that opts in to summary-view emission, but reality disagreed. `src/hippo/core/storage/view_generator.py` auto-emitted count + aggregate SQLite views for every non-abstract class during migration, with no annotation consumed. Nothing in the codebase consumed those views.
- **Alternatives considered:** (A) make the annotation a real opt-in by retiring auto-emission; (B) annotation-driven opt-out with auto-emission as default; (C) drop the annotation from sec9, keep auto-emission; (D) scrub summary views and the annotation entirely.
- **Chosen:** (D). No consumer existed; keeping dead DDL is not justified.
- **Actions landed:** Deleted `src/hippo/core/storage/view_generator.py`; removed the `generate_summary_views` call and import from `src/hippo/core/storage/migration.py`; removed `TestSummaryViews` from `tests/integration/test_partial_indexes_and_views.py` (partial-index tests retained, module docstring updated); removed the annotation from the sec9 §9.3 ASCII diagram, the sec9 §9.4 vocabulary table, and the sec9 §9.10 DDL-shim list; removed it from the `hippo-ext-vocabulary` proposal / tasks / draft `hippo_ext.yaml`; removed it from the `reference_hippo_ext.md` annotation list in `INDEX.md`.
- **Revert:** `view_generator.py` remains in git history (reachable from any commit before this one). To resurrect, restore the file, reinstate the call in `migration.py`, re-declare the annotation with a chosen option (A/B/C). The design-doc changes revert mechanically via `git revert`.

### Decision 9.4.B — Declare each annotation alongside its consumer; Wave 1 declares only annotations with live consumers [NEW 2026-04-19]

- **Finding (from the 2026-04-18 autonomous session):** `hippo_append_only` and `hippo_accessor` were drafted into `hippo_ext.yaml` during the Wave 1 `hippo-ext-vocabulary` change even though their consumers don't land until Wave 2 (`provenance-as-linkml-class`) and Wave 3 (`typed-client`) respectively. This leaves two annotations documented-but-inert for the duration between their declaration and their consumer.
- **Alternatives considered:** (A) declare all annotations up front in `hippo-ext-vocabulary`, with consumer wiring following in later waves; (B) declare each annotation with its consumer, bumping `hippo_ext`'s minor version in each change that adds one.
- **Chosen:** (B). Each OpenSpec change carrying both its annotation declaration and its consumer is more atomic. An agent reading `hippo_ext.yaml` at any point in time sees only live annotations, matching 9.2's principle that schema reflects actual behavior.
- **Consequences:** Wave 1 `hippo-ext-vocabulary` declares four annotations (`hippo_unique`, `hippo_index`, `hippo_index_partial`, `hippo_search`). Wave 2 `provenance-as-linkml-class` extends `hippo_ext` with `hippo_append_only`. Wave 3 `typed-client` extends with `hippo_accessor`. Each extension follows sec9 §9.4's four-step process (declare, implement, document, bump minor).
- **Actions landed:** Removed `hippo_append_only` and `hippo_accessor` from the Wave 1 draft `hippo_ext.yaml` (with a comment pointer to their owning changes). Updated the `hippo-ext-vocabulary` proposal's "Why" line, initial-vocabulary table, and tasks.md §1.2 to reflect four initial annotations. Updated sec9 §9.12's scope/deliverables/acceptance columns for `provenance-as-linkml-class` and `typed-client` to include their respective `hippo_ext` extension.
- **Revert:** Declare both annotations up front in Wave 1 (option A). Update the three Wave 1 files and the two §9.12 rows. Low blast radius.

### Decision 9.4.C — `hippo_search` declared with `range: string`, not a closed enum [NEW 2026-04-21]

- **Finding (during hippo-ext-vocabulary implementation):** sec9 §9.4's draft table showed `hippo_search` with value type `enum (fts5, …)`. The initial `hippo_ext.yaml` declared a `hippo_search_mode` enum with only `fts5` as a permissible value. Existing tests (`test_search_capability.py`, `test_fts_migration.py`) intentionally use non-`fts5` mode values (`embedding`, `fts`) to exercise adapter-layer validation — those tests failed at schema load with the new enum-backed validation.
- **Alternatives considered:** (A) keep the enum closed at `fts5`, rewrite the tests to assert on the new load-time failure path; (B) expand the enum to include every mode any adapter might support (impractical — the set is open across deployments); (C) loosen the range to `string`, let the adapter enforce which modes it supports.
- **Chosen:** (C). Matches sec9 §9.10's division of labor — schemas declare intent, adapters enforce capability. Different adapters (SQLite FTS5, PostgreSQL GIN, Neo4j full-text, future vector indexes) will genuinely support different modes; pinning a schema-level enum would force every deployment onto a single vocabulary.
- **Consequences:** `hippo_search` accepts any string value at schema load. A typo like `fts6` passes validation and fails later at adapter startup with "unsupported mode" — the error is clear and points at the right layer. sec9 §9.4, `reference_hippo_ext.md`, and the installed `hippo_ext.yaml` all reflect the `string` range; the `hippo_search_mode` enum has been removed entirely. Existing search-capability tests continue to pass unchanged.
- **Revert:** Reintroduce the `hippo_search_mode` enum and change `hippo_search.range` back to it. Rewrite `test_startup_raises_error_with_embedding_search_mode` and `test_fts_migration_planner::test_add_class_registers_fts_tables` to assert the schema-load-time failure instead of the adapter-startup failure. Moderate blast radius — any test fixture using an unsupported mode would need updating.

---

## 9.8 Typed Client

### Decision 9.8.A — Generation at `SchemaRegistry` load time, in-memory only

- **Alternatives:** (1) static file generation at build time; (2) runtime in-memory generation; (3) both.
- **Chosen:** (2) runtime in-memory. The generated Pydantic namespace is available under a stable SDK entry point after schema load.
- **Why:** Hippo's schema is deployment-specific; static generation would require a build step in user deployments. In-memory generation matches LinkML's own `PythonGenerator` patterns and avoids a second artifact to keep in sync.
- **Revert:** Add (1) as a supplementary path for IDE autocomplete if it becomes a felt need.

### Decision 9.8.B — Access pattern: dual-root + namespace-aware + nested-namespace support [FINALIZED 2026-04-18]

- **History:** Refined three times in sequence — (i) initial flat `client.samples.create(...)`; (ii) namespace-aware `client.<ns>.<accessor>.create(...)`; (iii) final form below. Left as a single entry with the history line so reviewers see the evolution without scanning for superseded versions.
- **Final form:**
  - Root-namespace classes accessible via both `client.<accessor>` (flat, default) and `client.root.<accessor>` (explicit). `client.root` is an alias; `root` is a reserved namespace name.
  - Non-root-namespace classes accessible via `client.<namespace>.<accessor>`.
  - Nested namespaces via dot notation: `namespace: assay.quant` is a literal string; the client splits on dots to produce `client.assay.quant`. No formal parent-child relationship between `assay` and `assay.quant` — the shared prefix is convention only, but the typed client presents them as a hierarchy.
  - Accessor default: `snake_case(ClassName) + "s"`. `hippo_accessor` annotation overrides per class.
  - FQN rule: last dot-separated segment is the class name; everything before is the namespace string. Dots in class names are rejected at load.
- **Collision detection (four cases, all load-time, actionable error templates):** same-namespace duplicate accessor; class accessor vs. sub-namespace segment; namespace name vs. SDK-reserved attribute; accessor vs. SDK-reserved name.
- **Why:** Preserves the schema's namespace structure (multi-namespace is the norm, contrary to an earlier mistaken assumption). Keeps root-level access flat and convenient per user guidance. Supports organizational nesting without introducing a formal parent-child model in LinkML (which has none). Makes collisions genuinely rare — a typical deployment, even a multi-namespace one, adds zero `hippo_accessor` annotations.
- **Supersedes sec3 decision "Root namespace canonicalization":** sec3 canonicalizes `root.X` to unqualified `X` at storage. sec9 keeps the flat-access convenience at the client level and adds the explicit `client.root.X` path. Storage-level canonicalization is untouched. The sec3 decision should be updated in INDEX.md to cite sec9 as the authoritative treatment.
- **Revert:** Revert to pure flat (no namespaces in the client) would break multi-namespace deployments; very high blast radius. Revert nested-namespace dot-splitting only is additive-compatible — collapses to flat strings on the client side with no schema changes needed.

### Decision 9.8.F — Nested namespaces via dot notation, no formal hierarchy [NEW 2026-04-18]

- **Alternatives:** (1) flat namespaces only (sec3 current state); (2) formal nested namespaces with declared parent-child relationships; (3) dot-notation-as-convention with client-side splitting.
- **Chosen:** (3). Namespace strings are literal (`"assay.quant"`); the typed client splits on dots for organizational convenience. `assay` and `assay.quant` are independent — the shared prefix is not a declared relationship.
- **Why:** LinkML has no native nested-namespace concept; any formal nesting would be a Hippo invention layered on top. The literal-string-with-client-side-splitting approach needs no new LinkML machinery, introduces no parent registration ceremony, and supports hierarchical organization where deployments want it. Risks (orphan parents, accessor/sub-namespace collisions) are manageable via load-time detection.
- **Revert:** Treat namespace strings as opaque in the client (no dot-splitting) — collapses nesting to flat attribute access. Additive-compatible; schemas don't need to change.

### Decision 9.8.G — FQN parsing rule: last dot-separated segment is the class name [NEW 2026-04-18]

- **Alternatives:** Explicit separator (e.g., `::`), last-dot rule, first-dot rule, require separate `namespace` and `class` fields in references.
- **Chosen:** Last-dot rule. `tissue.protocol.StepType` → namespace `tissue.protocol`, class `StepType`.
- **Why:** Unambiguous given the constraint that class names cannot contain dots (enforced at schema load). Human-readable. Consistent with how nested namespaces appear in the client.
- **Revert:** Change the separator rule and update schema validation; touches every FQN reference site. Moderate blast radius.

### Decision 9.8.E — Default accessor derivation rule: `snake_case(ClassName) + "s"` [NEW 2026-04-18]

- **Alternatives:** (1) inflect-library-backed plurals (handles irregulars but adds dependency and still misses some cases); (2) deterministic simple suffix rule; (3) no pluralization — use `snake_case(ClassName)` as-is.
- **Chosen:** (2). `snake_case` + `"s"`.
- **Why:** An LLM coding agent must be able to predict the accessor for any class without running code. The simple rule is perfectly predictable. Linguistic correctness is a non-goal; deployments that want `data` instead of `datums` use `hippo_accessor`.
- **Revert:** Change the default in the typed-client generator; user-schema changes only required on classes whose default accessor changes.

### Decision 9.8.C — Pydantic v2 only

- **Alternatives:** Support v1+v2 via conditional imports; v2 only.
- **Chosen:** v2 only.
- **Why:** LinkML's current `gen-pydantic` targets v2; v1 is past its maintenance window; dual-targeting doubles maintenance cost.
- **Revert:** Low likelihood; would require a wrapper layer.

### Decision 9.8.D — Generic `HippoClient` stays coequal (never "deprecated")

- **Alternatives:** Mark generic client as legacy once typed client lands; maintain both as first-class.
- **Chosen:** Both first-class (per 9.2 *Typed and dynamic coequal*).
- **Why:** Dynamic use cases (runtime schema discovery, tools, admin CLIs) need the generic client. No feature should land in one without the other.
- **Revert:** N/A — reversing this principle requires revisiting 9.2.

---

## 9.9 Validation Division of Labor

### Decision 9.9.A — Three-tier validation model with strict boundaries [CONFIRMED 2026-04-18]

- **Alternatives:** Two-tier (LinkML + Python); three-tier (LinkML + CEL + Python); fully custom.
- **Chosen:** Three-tier. LinkML for static shape; CEL for dynamic / cross-entity; Python plugin for what neither can express.
- **Why:** LinkML + CEL covers 95%+ of cases; Python escape hatch avoids blocking unusual requirements without encouraging custom code as a first resort. User confirmed the flexibility is needed; coding agents are expected to reach for Python only when CEL genuinely cannot express the rule.
- **Revert:** Remove the Python tier by declaring it deprecated; callers forced to CEL (which is strictly more analyzable).

### Decision 9.9.B — Execution order: LinkML → CEL → Python plugin, fail-fast by default

- **Alternatives:** Fixed order fail-fast; fixed order collect-all; configurable.
- **Chosen:** Fixed order (cheapest first) with an opt-in collect-all mode for batch ingest.
- **Why:** Fail-fast is the cheaper default; LinkML-level failures are almost always the root cause and bubble up clearly. Collect-all is useful for ingest pipelines that want to report every error in a batch.
- **Revert:** Change default to collect-all; callers opt in to fail-fast.

### Decision 9.9.C — Unified `ValidationResult` envelope across tiers [CONFIRMED 2026-04-18]

- **Alternatives:** Tier-specific result types; common envelope with tier annotation.
- **Chosen:** Common envelope, each failure annotated with its origin tier.
- **Why:** Callers consume results uniformly; origin is visible for debugging; tier-specific types would fragment the error surface.
- **Revert:** Split into per-tier types; callers would need a union.

---

## 9.10 LinkML Ecosystem Integration

### Decision 9.10.A — Adopt LinkML tools directly; strictly bound shims to `hippo_*` annotation effects [STRENGTHENED 2026-04-18]

- **Alternatives:** Adopt selectively and shim around weaknesses; adopt strictly and forbid shim drift.
- **Chosen (revised):** Adopt strictly. Shims exist for exactly one purpose — applying `hippo_*` annotation effects that LinkML generators have no knowledge of. Shims are explicitly NOT permitted for workarounds, bug-hiding, or selective reimplementation of LinkML capabilities. Expanding the shim surface requires a dedicated OpenSpec proposal.
- **Why (revised):** Allowing shim drift would slowly turn Hippo into a parallel LinkML reimplementation. The user made this explicit: LinkML tool versions are hard requirements; if LinkML needs fixing, upgrade LinkML, do not shim around it.
- **Revert:** Loosen the shim boundaries; permit workaround shims case-by-case. Risk: gradual drift into reimplementation.

### Decision 9.10.B — Pin LinkML to exact versions; LinkML patch bump triggers a Hippo version bump [STRENGTHENED 2026-04-18]

- **Alternatives:** Unpinned; pin to major; pin to minor; pin to exact version with release discipline.
- **Chosen (revised):** Exact-version pinning in `pyproject.toml` for LinkML and every LinkML tool dependency. Any LinkML version bump (including patch-level) requires the full Hippo test suite to pass before the pin is updated. Every LinkML pin update triggers a Hippo version bump even when Hippo source is unchanged — the released artifact is the combined `(Hippo, LinkML)` pair, and different LinkML ⇒ different artifact. Breaking LinkML changes that require Hippo source changes are scoped in an OpenSpec proposal before the pin moves.
- **Why (revised):** Reproducibility and auditability. Exact pins guarantee the same code runs the same way in every environment. Tying Hippo version to LinkML version ensures consumers can answer "what LinkML is in this Hippo release?" from the version number alone.
- **Revert:** Loosen to major-only pinning. Low revert cost in `pyproject.toml`; higher cost if Hippo's release infrastructure gets built around the bump-on-LinkML-bump rule.

### Decision 9.10.C — Upstream contribution for annotation patterns that prove general

- **Alternatives:** Keep everything in Hippo forever; contribute nothing; contribute eagerly.
- **Chosen:** Contribute when an annotation in `hippo_ext` demonstrates utility beyond Hippo and LinkML accepts such contributions.
- **Why:** Reduces long-term maintenance burden; aligns with "no shadow abstractions" principle at ecosystem scale.
- **Revert:** No revert needed — this is aspirational guidance.

---

## 9.11 Migration Narrative

### Decision 9.11.A — Narrative frame: three stages (pre-LinkML → SchemaRegistry seam → sec9 target)

- **Alternatives:** Simple "before/after"; detailed per-commit timeline; three-stage narrative.
- **Chosen:** Three-stage, matching 9.1's retrospective framing.
- **Why:** Most useful for an agent entering the codebase — names the stages, anchors recent refactors as "already done," points forward to sec9 target.
- **Revert:** Restructure as before/after; no cross-references depend on the staging.

### Decision 9.11.B — Cite specific commits by hash for already-done work

- **Alternatives:** Narrative only; cite commits.
- **Chosen:** Cite commits (consistent with 9.1).
- **Why:** Grounds the retrospective in observable history; agents reading git log can verify.
- **Revert:** Strip commit hashes if they become stale or misleading.

---

## 9.12 OpenSpec Decomposition

### Decision 9.12.A — 10 proposed OpenSpec changes, dependency-ordered

- **Alternatives:** Fewer, larger changes (3-4); more, smaller changes (15+); the chosen 10.
- **Chosen:** 10, grouped into three waves.
- **Why:** Each is independently reviewable and independently revertible. Fewer would mean each PR is too big; more would fragment related work.
- **Revert:** Merge or split any two adjacent changes without affecting others.

### Decision 9.12.B — Wave structure: foundation / data-model / consumer-facing

- **Alternatives:** Flat sequence; waves.
- **Chosen:** Waves. Wave 1 is foundation (vocabulary, core schema, IDs). Wave 2 is data model (Process, Provenance, temporal). Wave 3 is consumer-facing (validation clarification, typed client, REST).
- **Why:** Mirrors dependency structure naturally and lets the implementer pause between waves for validation.
- **Revert:** Drop the waves, keep the sequence — purely organizational.

### Decision 9.12.C — Per-change: scope, dependencies, deliverables, acceptance criteria

- **Alternatives:** Name and one-liner; full scoping per change.
- **Chosen:** Full scoping (consistent with openspec's expectations).
- **Why:** Enables an agent to pick up any change and execute without re-deriving scope.
- **Revert:** Strip to shorter form if overkill.

---

## 9.13 Non-Goals & Deferred Concerns

### Decision 9.13.A — Split into two groups: explicit non-goals, and deferred-for-later open questions [CONFIRMED 2026-04-18]

- **Alternatives:** One flat list; split.
- **Chosen:** Split. Non-goals are things sec9 explicitly excludes; deferred are things sec9 touches but doesn't finalize (ReferenceLoader shape, merge/fission primitives, etc.).
- **Why:** An agent can distinguish "don't do this" from "this is coming later."
- **Revert:** Merge into one list.

### Decision 9.13.B — Beyond the four user-confirmed non-goals, add three more discovered during drafting

- **Added non-goals:** no full PROV-O ontology import (only selective URIs); no human-readable IDs (UUIDs only); no first-class merge/fission primitives in this redesign.
- **Why:** These came up during the drafting pass and are worth making explicit so they don't silently get interpreted differently.
- **Revert:** Remove any individually.
