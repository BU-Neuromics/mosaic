# sec9 LinkML Redesign — Progress Report

**Session:** 2026-04-18 autonomous pass
**Worked by:** Claude
**Scope:** Steps 1–4 of the plan (consistency check, tag, INDEX update, Wave 1 OpenSpec scaffolding) + conservative exploration of the first implementation (step 5).

---

## What landed

### Commits on `main` (not pushed)

| SHA | Message |
|---|---|
| `c17733e` | `docs(hippo): add sec9 LinkML-centric redesign spec + decisions log` |
| (tag) | `design-pre-linkml` annotated tag at `c17733e` |
| `d47a8dc` | `docs(hippo): promote sec9 to approved in design index` |
| `a6d3cd7` | `docs(hippo): scaffold Wave 1 OpenSpec changes for LinkML redesign` |
| `50364cc` | `docs(hippo): draft hippo_ext.yaml + flag hippo_default migration work` |

Branch is 11 commits ahead of `origin/main`. Nothing pushed — your call on push timing.

### Design artifacts

- `design/sec9_linkml_redesign.md` — full 800-line design doc (unchanged from yesterday's review-complete state; two consistency tweaks to the 9.3 ASCII diagram and Layer contents table pulled `Process` into the stack inventory and dropped `hippo_default` from the illustration).
- `design/sec9_decisions.md` — decisions log, every entry tagged with review state (CONFIRMED / REVISED / STRENGTHENED / REFINED / FINALIZED / NEW) and date.
- `design/INDEX.md` — sec9 promoted from Proposed to Approved; sec9 + sec9_decisions added to Document Map; LinkML-Centric Redesign block reframed as "Approved — Implementation Underway"; Key Decisions Log gains eleven sec9 decisions (3-layer stack, hippo_ext vocabulary, Process, UUID identity, FQN parsing, provenance integrity, namespace-aware client, validation tiering, LinkML ecosystem); supersedes/reshapes Root namespace canonicalization and Provenance event model; resolves "Provenance system vs. entity events table split" open question.

### Wave 1 OpenSpec scaffolds

All four under `openspec/changes/`, each with `proposal.md` and `tasks.md`:

| Change | Status |
|---|---|
| `hippo-ext-vocabulary` | Scaffolded. Draft `hippo_ext.yaml` included as a design artifact (not yet installed in `src/`). Migration path for retiring `hippo_default` documented. |
| `hippo-core-schema` | Scaffolded. |
| `id-registry-and-uuid-strategy` | Scaffolded. |
| `process-class` | Scaffolded. |

Wave 2 (`provenance-as-linkml-class`, `computed-temporal-fields`) and Wave 3 (`validation-tiering-clarification`, `typed-client`, `reference-loader-shape`, `generated-rest-surface`) scaffolds are deferred until Wave 1 implementation is underway, per my operating rules for the session.

---

## Findings from the conservative exploration of `hippo-ext-vocabulary`

I deliberately stopped short of modifying `SchemaRegistry`, per the operating rules. Exploration surfaced three items that deserve your attention before the first OpenSpec change kicks off implementation:

### 1. `hippo_default` is live in the code; sec9 removes it

The following files read `hippo_default`:

- `src/hippo/linkml_bridge.py` (exports the `HIPPO_DEFAULT` constant)
- `src/hippo/core/storage/ddl_generator.py`
- `src/hippo/core/storage/pg_ddl_generator.py`
- `src/hippo/core/storage/migration.py`
- `src/hippo/core/storage/pg_migration.py`
- `src/hippo/core/storage/schema_diff.py`

sec9 §9.4 removed `hippo_default` in favor of LinkML's native `ifabsent`. Declaring `hippo_ext.yaml` without `hippo_default` would break any schema currently using the annotation. I updated `hippo-ext-vocabulary`'s proposal and tasks (new §6b) to scope the migration within this change:

1. Audit user schemas; migrate `hippo_default` → `ifabsent`.
2. Remove `HIPPO_DEFAULT` from `linkml_bridge.py`.
3. Update all five storage files to read `slot.ifabsent` instead.
4. Test that `ifabsent` produces equivalent DDL.

**Action item for you:** confirm this belongs inside `hippo-ext-vocabulary` rather than being a separate precursor change. My lean is "keep it here" — it's a small, tightly-coupled bit of work that makes the vocabulary declaration self-contained.

### 2. `hippo_summary_view` in sec9 vs. reality

sec9 §9.4 lists `hippo_summary_view` as a class-level annotation that opts in to summary-view emission. Reality: `src/hippo/core/storage/view_generator.py` auto-emits count + aggregate summary views for *every* non-abstract class with no annotation involved. There's no consumer for `hippo_summary_view` today.

Three ways to resolve:

- **A. Make `hippo_summary_view` opt-in.** Retire the auto-emission behavior in favor of annotation-driven. Requires a migration on deployments that rely on auto-emission (which is everyone, probably).
- **B. Make `hippo_summary_view: false` an opt-out.** Keep auto-emission by default but let schemas suppress.
- **C. Drop `hippo_summary_view` from sec9 entirely.** Auto-emission stays; no annotation is needed.

**Action item for you:** pick A / B / C. Without a decision, my draft `hippo_ext.yaml` declares the annotation with description matching option A, but there's no consumer wiring. I lean C — the simplest path — unless there's a real use case for controlling summary-view emission per-class.

### 3. `hippo_append_only` and `hippo_accessor` have no consumers yet

Both are new sec9 annotations with no current code reading them:

- `hippo_append_only` consumer lands in `provenance-as-linkml-class` (Wave 2).
- `hippo_accessor` consumer lands in `typed-client` (Wave 3).

Declaring them in `hippo_ext.yaml` without consumers is harmless — annotations without readers are just ignored. But they're declared in the current draft so that when Wave 2/3 changes set them on classes, validation doesn't fail with "undeclared annotation." Standard practice, not a blocker.

---

## Task list state

| # | Task | Status |
|---|---|---|
| 1 | Consistency-check pass on sec9 | completed |
| 2 | Apply `design-pre-linkml` git tag | completed |
| 3 | Promote sec9 to Approved in INDEX.md | completed |
| 4 | Scaffold OpenSpec: `hippo-ext-vocabulary` | completed |
| 5 | Scaffold OpenSpec: `hippo-core-schema` | completed |
| 6 | Scaffold OpenSpec: `id-registry-and-uuid-strategy` | completed |
| 7 | Scaffold OpenSpec: `process-class` | completed |
| 8 | Conservative exploration for `hippo-ext-vocabulary` kickoff | completed |
| 9 | Write status summary for user return | in progress (this file) |

---

## Recommended next steps when you return

1. **Review this progress doc and the three findings** — especially the `hippo_summary_view` question (needs a decision before implementation begins).
2. **Skim the four Wave 1 OpenSpec scaffolds** — each is under `openspec/changes/<name>/`. If scopes look right, any of them is ready to be picked up for implementation.
3. **Start implementation with `hippo-ext-vocabulary`** — the smallest, most self-contained change. Prerequisites done: draft schema exists; migration path for `hippo_default` documented; task list actionable. The first real code edits are in `src/hippo/linkml_bridge.py` (resource loading + validation hook) and the DDL generators (retiring `hippo_default`). This is the first change where it makes sense for a coding agent to take over.
4. **Push when ready** — 11 commits are queued locally. Nothing pushed because push is a shared-state action I didn't have standing to take autonomously.

---

## Things I deliberately did not do

- Did not push to `origin`.
- Did not modify `SchemaRegistry` (would have been invasive; flagged for you instead).
- Did not modify the DDL generators (same reason).
- Did not touch any existing user-schema fixtures (the `hippo_default` migration is scoped inside `hippo-ext-vocabulary` and belongs there, not in a pre-work commit).
- Did not scaffold Wave 2 or Wave 3 OpenSpec changes (per my operating rules — scaffold those as Wave 1 lands, to keep the backlog current rather than stale).
- Did not send a push notification. You were heading back anyway, and nothing rose to the "pull attention from whatever they're doing" bar.
