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

### Decision 9.7.E — `schema_version` derivation from `SchemaView.schema.version`, `"unversioned"` fallback [NEW 2026-04-21]

- **Finding (computed-temporal-fields implementation):** Sec9 §9.6 says the SDK captures `schema_version` from the merged `SchemaView` at write time. In a three-layer stack (`hippo_ext`, `hippo_core`, user schema), "the merged schema's version" isn't a single unambiguous string — each YAML file has its own `version:` field.
- **Chosen:** Read `registry.schema_view.schema.version` (the user schema's top-level `version:` field, after LinkML's merge resolves it). Fall back to the string literal `"unversioned"` when the user schema doesn't set one.
- **Alternatives considered:** (A) Composite string like `hippo_core-0.3.0+hippo_ext-0.2.0+user-1.2.3` — human-unfriendly, changes when any layer bumps, hard to filter queries on. (B) Content hash of the merged schema YAML — precise but opaque; breaks after whitespace changes; not useful for "what version was this written under" questions. (C) Require callers to supply a version string at write time — violates sec9's "caller cannot supply it."
- **Why (A)/(B)/(C) rejected:** All three trade simplicity for marginal precision. The user-schema-version interpretation matches how deployments already talk about versions ("we're on user-schema 1.2.3"); Hippo-internal version bumps are a separate, less-important dimension.
- **Plumbing:** `HippoClient.__init__` reads `registry.schema_view.schema.version or "unversioned"` when both a registry and storage are supplied; sets the adapter's `_schema_version`. Adapters constructed without a `HippoClient` (direct `SQLiteAdapter(db_path)`) start with `""` — the legacy transition state from Decision 9.6.F.
- **Revert:** Change the derivation in `HippoClient.__init__` (single line). No data migration needed — new rows would just carry a different string.

### Decision 9.7.F — Loud failure in `query()` mirrors `get()`: a single orphan poisons the whole page [NEW 2026-04-21]

- **Finding:** `HippoClient.get(entity_id)` raises `ProvenanceIntegrityError` on missing provenance per Decision 9.7.D. `HippoClient.query(entity_type)` returns a list; the natural implementation could either raise on the first inconsistency or skip the offending row and return the rest.
- **Alternatives considered:** (A) Raise — whole page fails if any entity is orphaned. (B) Skip — silently exclude orphaned entities from the result set, log a warning. (C) Include with null fields — the original pre-9.7.D soft-degradation behavior applied per-row.
- **Chosen:** (A). Mirrors `get()`. Per sec9 §9.2 *Provenance integrity is transactional and loud*, a corrupt audit log is a critical defect, not a row-level issue to absorb. A `query()` caller seeing 999 out of 1000 results silently is worse than seeing the exception and investigating.
- **Why (B) rejected:** "Silently return fewer rows than the user asked for" is indistinguishable from a legitimate empty result — caller can't tell why the row is missing. A tool that pages through results and skips corrupt rows would silently lose data.
- **Why (C) rejected:** Violates sec9 §9.2 explicitly. Already the pre-9.7.D behavior that was revised.
- **Operational note:** In a deployment that encounters integrity errors at read time, the fix is always *repair the adapter*, not *make the reader more permissive*. This decision makes that routing unambiguous.
- **Revert:** Switch to (B) by catching the exception inside the per-row loop. One-line change; backward-visible as a weakening of the invariant.

### Decision 9.7.G — `get_temporal` is a duck-typed adapter extension, not an abstract method [NEW 2026-04-21]

- **Finding:** `StorageAdapter.get_temporal(entity_ids)` is the batch primitive for sec9 §9.7 temporal aggregation. It's consumed by the SDK via `hasattr(self._storage, "get_temporal")` — SQLite and Postgres both implement it, but it's not declared on the `EntityStore` ABC.
- **Chosen:** Keep it duck-typed for now; do not add it to the abstract base class.
- **Why:** Matches existing precedent in the adapter layer (`get_fts_tables_for_entity_type`, `get_provenance_timestamps`, etc. are all duck-typed extensions). The `EntityStore` ABC already mandates the core read/write/find/history set; `get_temporal` sits alongside as a sec9-era extension. Non-relational adapters (Neo4j, when it lands) will need to decide whether they implement `get_temporal` natively or delegate — declaring it abstract up front would force a choice before the Neo4j constraints are understood.
- **Consequence:** SDK-side `hasattr` checks declare `get_temporal` optional; in practice, every concrete adapter implements it. If Neo4j (or a future adapter) doesn't, the SDK falls back to the entity's stored columns — same behavior as today for `query()` with a non-provenance-aware adapter.
- **Revert:** Promote to abstract on `EntityStore[T]` once all adapters are agreed. Low-cost later; additive-compatible for downstream subclassers since all existing concrete classes already implement it.

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

## 9.5 `hippo_core` Schema

### Decision 9.5.A — Keep `is_available` hardcoded as a fallback when not induced [NEW 2026-04-21]

- **Finding (during hippo-core-schema implementation):** sec9 §9.5 declares `is_available` as a required slot on Entity, flowing into every domain class via `is_a: Entity`. DDLGenerator and PostgresDDLGenerator previously hardcoded the column unconditionally. With the schema-driven path, the column should come from induced_slots — but many test fixtures use `build_registry` to construct ad-hoc classes without `is_a: Entity`, and their tests rely on `is_available` being present in the generated DDL.
- **Alternatives considered:** (A) require all schemas (including ad-hoc test fixtures) to use `is_a: Entity`; (B) keep the hardcoded column as an unconditional fallback; (C) keep it as a fallback only when the class didn't already declare `is_available` via induction.
- **Chosen:** (C). Classes that inherit from Entity get `is_available` through the normal slot path; classes that don't fall through to a hardcoded append. Preserves the sec9 design goal (schema is source of truth) for proper schemas while keeping existing tests working without a sweeping migration.
- **Consequences:** `DDLGenerator._build_table` and `PostgresDDLGenerator._build_table` check `existing_column_names` before appending a hardcoded `is_available`. `superseded_by` remains unconditionally hardcoded; sec9 §9.6's provenance redesign will remove it in Wave 2.
- **Revert:** Remove the guard, restore unconditional hardcoding. Low blast radius. The principled alternative — Option A, requiring `is_a: Entity` everywhere — is deferred until Wave 2 consolidation of test fixtures.

### Decision 9.5.B — `slot_default()` helper coerces boolean `ifabsent` strings [NEW 2026-04-21]

- **Finding:** LinkML stores `ifabsent` as a string even for boolean slots (`ifabsent: "true"` / `"false"`). DDL generators format defaults via `_format_default(value)`; passing a raw string produces `DEFAULT 'true'` — a quoted string literal, not a native boolean — which is wrong for SQLite (`1`/`0`) and Postgres (`TRUE`/`FALSE`).
- **Alternatives considered:** (A) make `_format_default` LinkML-ifabsent-aware, parsing `"true"`/`"false"`/`"int(0)"`/`"uuid()"` inline; (B) a thin `slot_default(slot)` helper in `linkml_bridge` that coerces known LinkML ifabsent forms to Python values; (C) change `hippo_core` to use `ifabsent: "1"` / `"0"` instead of `"true"` / `"false"`.
- **Chosen:** (B), minimal form. Current coverage: `range: boolean` + `ifabsent` in `{"true", "false"}` returns Python `True`/`False`; everything else passes through unchanged. Richer parsing (integer/datetime/uuid constructor forms) is deferred until a concrete slot needs it.
- **Consequences:** `slot_default()` lives in `hippo.linkml_bridge` and is called by `DDLGenerator`, `PostgresDDLGenerator`, `migration.py`, and `pg_migration.py`. Schema authors write `ifabsent: true` in their YAML (standard LinkML idiom) and the DDL output is native SQL on both adapters.
- **Revert:** Inline the coercion at each call site or expand `_format_default` to handle ifabsent forms. The helper is a thin wrapper; removing it is mechanical.

### Decision 9.5.C — `_flatten_for_validator` materializes imports inline for `linkml.validator` [NEW 2026-04-21]

- **Finding:** LinkML's `Validator` (and `JsonschemaValidationPlugin`) resolve `imports:` independently of `SchemaView`'s `importmap`. When the user schema says `imports: [hippo_core]` and hippo_core lives outside the user-schema directory (inside `src/hippo/schemas/` as a bundled resource), the validator tries to open `hippo_core.yaml` relative to the user schema's directory and fails with `FileNotFoundError`. `SchemaView.materialize_derived_schema()` re-triggers the same import resolution.
- **Alternatives considered:** (A) pass the importmap to `Validator` (not supported in the current `linkml.validator` API); (B) pre-flatten the merged `SchemaView` into a self-contained dict with all classes/slots/enums/types inlined and `imports:` stripped, then hand that dict to `Validator`; (C) write the merged schema to a temp file with all imports resolved, then load from there.
- **Chosen:** (B). A module-level `_flatten_for_validator(sv)` helper reads `sv.all_classes(imports=True)`, `sv.all_slots(imports=True)`, `sv.all_enums(imports=True)`, `sv.all_types(imports=True)`, dumps each via `yaml_dumper`, and rebuilds a flat dict with only `linkml:types` as an import. The dict is passed to `Validator` which no longer needs to resolve imports from disk.
- **Consequences:** `Validator` works regardless of where `hippo_core` lives on disk. Flattening runs once per `SchemaRegistry` construction (schema load is already a slow path; the extra round-trip is negligible). No behavior change visible to callers.
- **Revert:** Pass `sv.schema` directly to `Validator` again. Would break any setup where bundled schemas are imported, so not a practical revert.

### Decision 9.5.D — id-registry scope narrowed: existing `entities` table IS the registry [NEW 2026-04-21]

- **Finding (during id-registry-and-uuid-strategy implementation):** sec9 §9.5 and the `id-registry-and-uuid-strategy` proposal scope a new `_entity_registry` table with `(id, entity_type, created_at)`, populated transactionally on every entity create. Reality: the current SQLite and PostgreSQL adapters already store all entities in a single `entities` table with `id`, `entity_type`, `data` (JSON), and friends. The type discriminator `entity_type` is already maintained, already indexed (via primary key on id), and already populated transactionally with entity writes. A separate `_entity_registry` would be redundant against this design.
- **Alternatives considered:** (A) add `_entity_registry` anyway, keeping it in sync with the `entities` table (duplicate data + extra write); (B) use the `entities` table as the registry and expose SDK helpers (`resolve_type`, `resolve_types`) that wrap it; (C) defer the whole id-registry change until the storage model is consolidated (per-type-table vs. single-entities-table).
- **Chosen:** (B). The existing `entities` table serves the exact purpose a `_entity_registry` would — id → entity_type lookup — without duplicate data. SDK helpers wrap the existing query so callers use the sec9 API surface (`client.resolve_type(uuid)`); if the storage model later migrates to per-type tables, the helpers become the stable seam and the registry implementation switches underneath without callers noticing.
- **Consequences:** `SQLiteAdapter.resolve_type` / `resolve_types` and `PostgresAdapter.resolve_type` / `resolve_types` added. `HippoClient.resolve_type(uuid)` and `HippoClient.resolve_types(uuids)` added. No new table, no backfill migration, no write-path changes. Performance-benchmark task from the proposal is obsolete (the lookup path hasn't changed — it's the same SELECT the adapter already uses for read).
- **Deferred parts of the proposal:** UUID pattern on `Entity.id` (would break existing test fixtures using ids like "s1"; postpone until a test-fixture cleanup pass); `client.get(uuid)` overload without `entity_type` (requires deeper restructuring of `QueryService` which routes by entity_type today); one-time backfill migration (unnecessary — the `entities` table always had the type column).
- **Revert:** Remove the four methods (two adapters × {single, batch}) and two client methods. Low blast radius.

---

## 9.6 Provenance as a LinkML Class

### Decision 9.6.A — Split `provenance-as-linkml-class` into declaration-only + dedicated `provenance-migration` change [NEW 2026-04-21]

- **Finding (Wave 2 kickoff):** The original `provenance-as-linkml-class` proposal bundled the LinkML declaration of `ProvenanceRecord` with the storage migration. The legacy `ProvenanceStore` + `provenance` table has ~40 deeply-coupled test references and concepts sec9 §9.6 doesn't model (`previous_state_hash`, `state_snapshot`, `operation_id` as a separate field, `source`). Bundling all of that into one OpenSpec change would make the opinionated calls about legacy-field retirement (drop vs. preserve) invisible — they'd be buried inside a sprawling change.
- **Alternatives considered:** (A) Full rewrite now — declare `ProvenanceRecord` in `hippo_core`, rewrite `ProvenanceStore`, migrate ~40 tests in one change. (B) Narrow — declare only, keep `ProvenanceStore` on the legacy `provenance` table indefinitely. (C) Staged — declare only now as `provenance-as-linkml-class`; split the storage migration into a dedicated `provenance-migration` change where the legacy-field retirement decisions get explicit review.
- **Chosen:** (C). The LinkML declaration has independent value (introspection, typed-client support in Wave 3, `hippo_append_only` annotation lands in the vocabulary, `Operation` enum becomes importable). Splitting the migration into its own change makes the opinionated calls (drop `previous_state_hash`, drop `state_snapshot`, rename `user_context` → `actor_id`, etc.) reviewable in isolation.
- **Consequences:** `provenance-as-linkml-class` is scoped to: declare `hippo_append_only` in `hippo_ext` (0.1.0 → 0.2.0); declare `ProvenanceRecord` in `hippo_core` (0.2.0 → 0.3.0) with all sec9 §9.6 slots including `class_uri: prov:Activity` and `hippo_append_only: true`; update reference docs; tests for the declaration. Adapter-side enforcement and `ProvenanceStore` rewrite move to the new `provenance-migration` change. sec9 §9.12 decomposition updated from 10 changes to 11; the Wave 2 dependency graph now reads `provenance-as-linkml-class → provenance-migration → computed-temporal-fields`.
- **Revert:** Merge `provenance-migration` back into `provenance-as-linkml-class`. Low-cost but doesn't address the scope concern that motivated the split.

### Decision 9.6.B — Legacy operation-string mapping to the `Operation` enum [NEW 2026-04-18]

- **Finding (provenance-migration commit 2 prep):** A grep across `src/hippo/` surfaces eleven distinct operation strings passed to `ProvenanceStore.record()`, not the six the sec9 §9.6 `Operation` enum declares. The extras (`"EntitySuperseded"`, `"EntityUpdated"`, `"REPLACED"`, `"RELATE"`, `"UNRELATE"`, `"AvailabilityChanged"`) accreted as ad-hoc strings in different subsystems over time. A mechanical rename would lose semantic information; each call site needs per-site review.
- **Per-site mapping table** (verified by reading each call site):

  | Legacy string | Site | sec9 `Operation` | Notes |
  |---|---|---|---|
  | `"CREATE"` | sqlite_adapter.py:1190, postgres_adapter.py:1093 | `create` | direct map |
  | `"UPDATE"` | ingestion_service.py:174 | `update` | direct map |
  | `"EntityUpdated"` | provenance_service.py:190 | `update` | entity fields modified |
  | `"REPLACED"` | ingestion_service.py:299 | `update` | ingest-replace semantics: same entity_id, new data — not supersession (which requires distinct replacement_id) |
  | `"EntitySuperseded"` | provenance_service.py:173 | `supersede` | `derived_from_id` now carries the replacement; patch retains `{reason}` |
  | `"AvailabilityChanged"` | ingestion_service.py:420 | `availability_change` | patch carries `{is_available, reason}` |
  | `"SOFT_DELETE"` | sqlite_adapter.py:1305, postgres_adapter.py:1203 | `availability_change` | patch carries `{status: "deleted"}` per sec9 §9.6 |
  | `"RELATE"` | relationship.py:158 | `relationship_add` | patch carries `{slot, target_id}` |
  | `"UNRELATE"` | relationship.py:229 | `relationship_remove` | patch carries `{slot, target_id}` |
  | `"external_id_add"` | future | `external_id_add` | |
  | `"external_id_remove"` | future | `external_id_remove` | |

- **Chosen:** Apply the mapping table above at rewrite time. A small `_legacy_operation_string_map: dict[str, Operation]` helper lives in `ProvenanceStore` for the transition period; removed once all callers pass `Operation` enum values natively.
- **Why:** The per-site review surfaces the `"REPLACED"` nuance (mapped to `update`, not `supersede`) and the `"EntitySuperseded"` lineage (now carries `derived_from_id` instead of a patch field). Both are judgment calls that a mechanical rename would have missed.
- **Revert:** Per-row. If a caller wants different semantics, change the site and update the table.

### Decision 9.6.C — SQL triggers are the enforcement mechanism for `hippo_append_only`, not adapter-level Python checks [NEW 2026-04-18]

- **Finding:** The provenance-migration proposal said "adapter write-guard" for `hippo_append_only`. Reading the existing code, the legacy `provenance` table is already protected by five SQLite triggers (`sqlite_triggers.py`) that RAISE ABORT on UPDATE / DELETE. Adapter-level Python checks are strictly weaker — direct-SQL access (e.g., from `sqlite3` CLI or a raw-connection backdoor) bypasses them; DB triggers don't.
- **Alternatives considered:** (A) Keep adapter-level Python checks only (weaker than status quo, but simpler). (B) Keep triggers, rename to target the new `ProvenanceRecord` table with new column names. (C) Extend the DDL generator to emit triggers from `hippo_append_only` — fully schema-driven. (D) Both — triggers for SQL-level enforcement plus adapter-level Python check for clearer error messages.
- **Chosen:** (B) for provenance-migration commit 2; (C) is the long-term target for a future change. (B) preserves the current security posture without extending the DDL generator scope mid-migration.
- **Why (B) over (A):** Not weakening existing protection is a strict correctness win. Rename is mechanical: change `provenance` → `ProvenanceRecord`, `entity_id` → `id`, drop `user_context` and `payload` triggers (absorbed by the generic "no UPDATE" behavior via BEFORE UPDATE without a target column).
- **Why (B) over (C):** DDL-generator extension is a separate capability with its own acceptance criteria (applies to other `hippo_append_only` classes in user schemas, needs Postgres parity, etc.). Scope creep into commit 2 risks pulling the rewrite further behind.
- **Why (B) over (D):** Duplicate enforcement creates drift risk. If the triggers fire, the Python check never runs; if the Python check runs, the triggers haven't fired either. Single source of truth (SQL triggers) is cleaner.
- **Consequences for commit 2:**
  - `sqlite_triggers.py`: retarget from `provenance` to `ProvenanceRecord`; drop the column-specific UPDATE triggers in favor of a single BEFORE UPDATE trigger (any column, any row).
  - `SchemaRegistry.append_only_classes()` (landed in commit 1) is not consumed by adapters in commit 2 — it remains available for the future (C) work and for non-SQL adapters (Neo4j, etc.).
  - Postgres: equivalent `CREATE TRIGGER` replaces the "Postgres equivalent" adapter check mentioned in the proposal.
- **Revert:** Move to (A) by dropping the triggers module and adding Python-level checks. Backward-visible as a security downgrade.

### Decision 9.6.D — `ProvenanceRecord` table is DDL-generated via LinkML, not hand-coded [NEW 2026-04-18]

- **Finding (commit 1 verification):** `DDLGenerator().generate(registry)` against a registry importing `hippo_core` already emits a correct `ProvenanceRecord` table — all sec9 §9.6 columns present, NOT NULL on required slots, indexes on `hippo_index`-annotated slots, FK from `process_id` to `Process`. No generator changes required.
- **Chosen:** `SQLiteAdapter._init_schema` (and Postgres equivalent) drops the hand-coded `CREATE TABLE IF NOT EXISTS provenance (...)` block and the supporting `CREATE INDEX` statements; the `ProvenanceRecord` table comes in through the existing LinkML-DDL pipeline (same path used for domain classes). The adapter's startup code ensures that pipeline runs against a registry that includes `hippo_core`.
- **Why:** Matches sec9 §9.2 principle (every class goes through the same DDL path). Hand-coded DDL diverging from the LinkML declaration is exactly the drift risk the sec9 redesign is meant to eliminate.
- **Consequences:** The `entities` / `relationships` / `entity_external_ids` / `schema_version` tables remain hand-coded for now (they're out of scope for this change; their LinkML-class migration is separate work in Wave 3). Only the `provenance` table and its indexes are removed from the hand-coded block.
- **Revert:** Restore the hand-coded DDL block; remove `ProvenanceRecord` from the merged registry that the adapter uses for LinkML DDL generation.

### Decision 9.6.F — Known transition-period fallbacks flagged explicitly [NEW 2026-04-18]

- **Finding:** Two semantic-contract compromises are active during the provenance-migration transition that sec9 §9.6 should eventually eliminate. Flagging them explicitly here so they don't ship as silent "done."
- **Fallback 1 — ``actor_id = "unknown"`` sentinel for new rows from unmigrated callers.** ``ProvenanceStore.record()`` defaults ``effective_actor`` to the literal string ``"unknown"`` when the caller passes ``None``. Several unmigrated src/ call sites (``ingestion_service.py``'s update paths, ``sqlite_adapter.create`` when ``user_context=None``) currently produce rows with ``actor_id = "unknown"``. Sec9 §9.5's identity model requires ``actor_id`` to be a UUID resolving to an agent entity. Follow-up: migrate those call sites to require a real ``actor_id`` (probably via the future service-context infrastructure); remove the fallback.
- **Fallback 2 — ``schema_version = ""`` on every new row.** Sec9 §9.6 specifies that the SDK captures ``schema_version`` from ``SchemaRegistry`` at write time. The adapter's ``ProvenanceStore.__init__`` accepts a ``schema_version`` parameter but neither ``SQLiteAdapter`` nor ``PostgresAdapter`` thread a registry through at construction, so every new row's ``schema_version`` column is an empty string. NOT NULL is satisfied syntactically; the semantic contract is not. Follow-up: plumb the registry (or a schema-version string derived from it) into both adapters, populated at adapter construction or on first write after schema load.
- **Why (tracking, not fixing now):** Both fallbacks are additive-compatible — removing them later won't require a data migration (new rows would just get richer values). Fixing them in this commit would expand the blast radius beyond "rewrite the provenance layer" into "propagate a schema registry through construction" and "plumb per-request actor context" — both multi-day undertakings on their own.
- **Revert / fix-forward:** Not applicable (these are known gaps to close, not decisions to revert).

### Decision 9.6.E — Legacy `user_context` strings are not back-populated to `actor_id` UUIDs [NEW 2026-04-18]

- **Finding (from the provenance-migration proposal's open question):** Legacy rows have `user_context` as a free-form string (often a username or `"sqlite_adapter"`). After rename to `actor_id`, these strings won't resolve through the UUID identity model (sec9 §9.5).
- **Alternatives considered:** (A) Leave as-is — historical audit records retain their historical actor strings; new records use UUIDs. (B) Synthesize a `LegacyActor` placeholder entity per unique legacy string and back-populate references.
- **Chosen:** (A). Simpler; matches append-only semantics (you don't rewrite history); legacy rows are a finite, read-only population that doesn't need forward compatibility with the identity model.
- **Why:** Back-population (B) conflicts with the append-only invariant — rewriting `actor_id` across a million legacy rows is a mass mutation of an audit log, which is exactly what the immutability triggers reject. Even if triggers were temporarily disabled for the migration, the resulting synthetic `LegacyActor` entities are clutter with no consumer. Since there are no production deployments (per earlier user directive), the population of legacy rows is near-empty or easily droppable.
- **Revert:** (B) remains available as a follow-up migration; low cost.

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
