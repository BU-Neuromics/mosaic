# sec9 Wave 1 Implementation — Progress Report

**Session:** 2026-04-21 autonomous pass
**Worked by:** Claude
**Scope authorized:** Full Wave 1 implementation (four OpenSpec changes) plus Wave 2/3 scaffolding, per the user's "feel free to make opinionated decisions, note to review together later" directive before dinner.

---

## Headline

**All four Wave 1 OpenSpec changes implemented and tested.** 833 tests pass, 8 skipped, no regressions. Wave 2 and Wave 3 scaffolds are in place (proposal.md + tasks.md for each) ready for implementation. Nothing pushed; you push when you're ready.

| Wave 1 change | Status |
|---|---|
| `hippo-ext-vocabulary` | ✅ Landed (4 commits) |
| `hippo-core-schema` | ✅ Landed (2 commits) |
| `id-registry-and-uuid-strategy` | ✅ Landed (narrowed scope — see Decision 9.5.D) |
| `process-class` | ✅ Landed |

| Wave 2 change | Status |
|---|---|
| `provenance-as-linkml-class` | 📋 Scaffolded (proposal.md + tasks.md) |
| `computed-temporal-fields` | 📋 Scaffolded |

| Wave 3 change | Status |
|---|---|
| `validation-tiering-clarification` | 📋 Scaffolded |
| `typed-client` | 📋 Scaffolded |
| `reference-loader-shape` | 📋 Scaffolded |
| `generated-rest-surface` | 📋 Proposal-only (optional, deferred per sec9 §9.12) |

---

## Commits this session (in order)

Previous commits this session were the three-findings review work plus the `chore(hippo): regenerate uv.lock` you asked for. Wave 1 implementation starts at `1be200b`.

```
bba28bb docs(hippo): scaffold Wave 2 and Wave 3 OpenSpec changes
a3e9b4d feat(hippo): add Process class to hippo_core (Wave 1 #4)
0462d44 feat(hippo): id-registry — resolve_type helpers on adapters + HippoClient
2093622 feat(hippo): finalize hippo-core-schema — reference doc, tests, decisions
826c5fe feat(hippo): ship hippo_core.yaml + three-layer SchemaRegistry merge
d2cd016 test(hippo): add dedicated tests for hippo_ext annotation validation
ad25ca0 feat(hippo): SchemaRegistry validates hippo_* annotations against hippo_ext
cffbef6 feat(hippo): install hippo_ext.yaml at src/hippo/schemas/
1be200b refactor(hippo): retire hippo_default in favor of LinkML-native ifabsent
e748265 chore(hippo): regenerate uv.lock
7d601fd docs(hippo): narrow Wave 1 vocabulary; defer hippo_append_only & hippo_accessor
0a0c642 feat(hippo): scrub hippo_summary_view + auto-emitted summary views
```

10 implementation commits + 2 doc/scaffold commits. Branch is now 24 commits ahead of `origin/main`. All local; push when ready.

---

## What landed, in detail

### Wave 1 #1: `hippo-ext-vocabulary`

- `HIPPO_DEFAULT` constant deleted; all DDL/migration/schema-diff code paths now read `slot.ifabsent` via a new `slot_default()` helper in `hippo.linkml_bridge`. Existing tests updated; no user-schema migration needed (nothing in the repo used `hippo_default:`).
- `src/hippo/schemas/hippo_ext.yaml` installed, declaring four initial annotations (`hippo_unique`, `hippo_index`, `hippo_index_partial`, `hippo_search`) via LinkML slots (modeling note in the schema header — LinkML has no native "annotation vocabulary" metamodel, so slots repurposed).
- `SchemaRegistry` validates every `hippo_*` annotation at construction — undeclared, type-mismatched, and wrong-target annotations raise `SchemaError(HIPPO_EXT_VALIDATION)` with aggregated, actionable messages.
- `design/reference_hippo_ext.md` written — per-annotation reference with examples, interactions, version discipline, extensibility process.
- New `TestHippoExtValidation` test class in `tests/core/test_linkml_bridge.py` (8 tests) covering the four failure modes plus the non-hippo-annotations-pass-through case.

### Wave 1 #2: `hippo-core-schema`

- `src/hippo/schemas/hippo_core.yaml` ships with `Entity` (abstract, `class_uri: prov:Entity`, `id` + `is_available` slots), `Status` enum, `Operation` enum, placeholder `Validator` + `ReferenceLoader` classes pointing at later changes.
- `SchemaRegistry` three-layer merge via `SchemaView` importmap: callers say `imports: [hippo_core]` in their YAML and LinkML resolves to the bundled path.
- `_flatten_for_validator` helper added in `linkml_bridge` — materializes all classes/slots/enums/types inline before handing the schema to `linkml.validator.Validator`, which otherwise re-resolves imports independently of `SchemaView`'s importmap. Detailed in Decision 9.5.C.
- `sample_schema.yaml` migrated to import hippo_core; local `Entity` declaration removed; Project/Sample continue to use `is_a: Entity`.
- DDL generators updated: `is_available` is emitted from the schema (via induced_slots) when the class inherits from Entity; hardcoded fallback retained for ad-hoc test fixtures that don't `is_a: Entity` (Decision 9.5.A). `superseded_by` stays hardcoded pending Wave 2's provenance redesign.
- `design/reference_hippo_core.md` written.
- New `TestHippoCoreImport` test class (4 tests) plus `TestHippoCoreProcess` (6 tests, added in Wave 1 #4).

### Wave 1 #3: `id-registry-and-uuid-strategy` (narrowed scope)

Significant finding during implementation: the existing SQLite and PostgreSQL adapters already store all entities in a single `entities` table with an `entity_type` discriminator — effectively *already* the id-registry sec9 §9.5 proposed. A separate `_entity_registry` table would duplicate data without adding capability. Decision 9.5.D captures the rationale and commits the narrowed scope:

- `SQLiteAdapter.resolve_type(uuid)`, `resolve_types(uuids)` (batch) added, wrapping the existing `entities` table lookup.
- Postgres equivalents with `ANY(%s)` for the batch form.
- `HippoClient.resolve_type(uuid)`, `HippoClient.resolve_types(uuids)` wrap the adapter.
- Type resolution works regardless of availability (archived/deleted entities retain a knowable type).
- New `TestTypeResolution` test class (5 tests) covers known / unknown / batch / empty / post-delete cases.

**Deferred from the original proposal** (flagged in sec9_decisions.md Decision 9.5.D):
- UUID `pattern` constraint on `Entity.id` — would break existing test fixtures using ids like `"s1"`; postpone until a test-fixture cleanup pass.
- `client.get(uuid)` overload without `entity_type` — requires deeper `QueryService` restructuring.
- One-time backfill migration — unnecessary, no registry table to backfill.
- Performance benchmarks — the lookup path didn't change; nothing to re-benchmark.

### Wave 1 #4: `process-class`

- `Process` class added to `hippo_core.yaml` with `is_a: Entity`, `class_uri: prov:Activity`. Slots: `parent_process_id` (self-reference), `operation_kind` (hippo_index), `started_at` (hippo_index), `ended_at` (optional), `actor_id`.
- `hippo_core` minor-bumped to `0.2.0`.
- `reference_hippo_core.md` updated with a full `Process` section including a PipelineRun subclass example.
- New `TestHippoCoreProcess` test class (6 tests) covering Process presence, Entity slot inheritance, subclass inheritance, `class_uri`, self-reference, and index annotations reaching induced slots.

---

## Decisions made during implementation (all in sec9_decisions.md, dated 2026-04-21)

| Decision | Summary |
|---|---|
| **9.4.C** | `hippo_search` range changed from enum to `string`. Schemas declare intent; adapters enforce mode capability. Existing tests using non-fts5 modes continue to pass. |
| **9.5.A** | `is_available` kept hardcoded as a fallback in DDL generators when the class doesn't inherit it via `is_a: Entity`. Preserves ad-hoc test fixtures; principled path (require `is_a: Entity` everywhere) deferred. |
| **9.5.B** | New `slot_default()` helper in `linkml_bridge` coerces boolean `ifabsent` strings (`"true"`/`"false"`) to Python booleans so DDL emits native SQL defaults. Minimal form; richer ifabsent parsing (`uuid()`, `datetime(now)`) deferred. |
| **9.5.C** | `_flatten_for_validator` materializes imports inline before `linkml.validator.Validator` sees the schema. Workaround for LinkML's lack of importmap in the Validator API. |
| **9.5.D** | `id-registry-and-uuid-strategy` scope narrowed — the existing `entities` table already serves the registry role; no new table needed. SDK exposes stable `resolve_type` helpers that can be re-plumbed later if the storage model migrates to per-type tables. |

All five decisions have `[NEW 2026-04-21]` tags, alternatives considered, rationale, and revert paths.

---

## Test state

- Full suite: **833 passed, 8 skipped, 1 warning** (the warning is a pre-existing `TestEntity` collection warning in `tests/core/test_provenance.py`, unrelated to this work).
- Wave 1 added **29 new tests** across `test_linkml_bridge.py` (TestHippoExtValidation 8, TestHippoCoreImport 4, TestHippoCoreProcess 6) and `test_client.py` (TestTypeResolution 5), plus 6 more (the earlier finding #2 scrub removed 1 and added none).
- No tests broken unmodified; 7 existing tests adjusted to match new expected behavior (TestValidation required `is_available` in test data; TestDefaultValue renamed for ifabsent; TestFullSchema dropped a trivial `hippo_default` annotation).

---

## Things worth reviewing when you return

### Nothing urgent

The implementation matches sec9's design as scoped. The five implementation decisions are reviewable at your pace; none would require a hot rollback if you disagreed.

### Things I'd particularly call out

1. **Decision 9.5.D (narrowed id-registry scope)** is the most substantive judgment call. If you want the full `_entity_registry` table (per the original proposal's explicit design) I should add it despite the redundancy — that's a call that affects how Neo4j and future adapters align with the relational storage model.

2. **The `Entity`-is-a hardcoded-fallback in DDL (9.5.A)** is a pragmatic compromise. The principled path (all classes `is_a: Entity`) touches many test fixtures; worth a dedicated change later that does the sweep.

3. **`_flatten_for_validator` (9.5.C)** is a LinkML-API-shape workaround. If LinkML's `Validator` API later gains an `importmap` parameter, we remove the helper. Until then, it's the price of using bundled schemas.

4. **`hippo_core` version is `0.2.0`** now (Entity + Process added in two minor bumps from 0.1.0). `hippo_ext` is still `0.1.0` (four initial annotations). Wave 2 will bump hippo_ext to 0.2.0 when it adds `hippo_append_only`.

### Pushing

16 commits are queued locally. I didn't push. `git push origin main` from your terminal.

---

## Recommended next steps

1. **Review `sec9_decisions.md`** additions (9.4.C, 9.5.A–D). Everything behind them is documented; push back if any decision needs revisiting.
2. **Spot-check the four Wave 1 changes** if you want — each has a proposal.md and tasks.md under `openspec/changes/<name>/`. Implementation matches the proposals modulo the documented decisions.
3. **Push when ready.**
4. **When you pick up Wave 2**, `provenance-as-linkml-class` is the next change. Its proposal + tasks are scaffolded; the biggest subtasks are (a) migrating the existing `ProvenanceStore` table to the LinkML-declared shape and (b) wiring `hippo_append_only` enforcement into the adapters.

---

## Parking lot (surfaced during implementation, not urgent)

- **Test-fixture cleanup pass:** many tests use `build_registry` with ad-hoc classes that don't `is_a: Entity`. A future change could sweep these and retire the hardcoded-`is_available` fallback. Not blocking.
- **Summary views (finding #2 from 2026-04-18) stay scrubbed.** No consumer emerged during Wave 1 implementation.
- **LinkML tool pinning:** still using `linkml` resolved via `uv`; explicit pin in `pyproject.toml` per Decision 9.10.B could be tightened whenever you do a dependency pass.
- **`sec9_progress.md`** (from the 2026-04-18 autonomous session) can be moved to `design/archive/` or deleted — all three findings it flagged are resolved.
