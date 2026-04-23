# sec9 LinkML Migration — Handoff Doc

**Written:** 2026-04-22 (end-of-session, in transit)
**Purpose:** Single entry point for the next development session. Read this first; it points at everything else.

---

## TL;DR

- **sec9 Wave 1, 2, and 3** are complete modulo one change (`reference-loader-shape`) that's blocked on a design discussion.
- **898 tests pass**, 7 skipped (non-Postgres-integration). Full suite green at every recent commit.
- **21 commits are unpushed.** `git log origin/main..HEAD` lists them. Push from the terminal when ready; none of the work is live until then.
- **6 documented deferred follow-ups** (itemized below). None is architecturally contentious; each is small-to-medium.

---

## Where to look for authoritative details

| Question | File |
|---|---|
| What was decided and why? | `design/sec9_decisions.md` — 25+ entries, 9.4.A → 9.10.B |
| What's the governing design? | `design/sec9_linkml_redesign.md` — §9.12 decomposition table, §9.1–9.11 prose |
| What landed in each wave? | `design/sec9_progress_2026-04-21_wave2.md`, `design/sec9_progress_2026-04-22_wave3.md` |
| What's the state of each OpenSpec change? | `openspec/changes/<change>/tasks.md` — checkbox items with deferred callouts |
| What changed in the last session (this one)? | This file, below + commits `9ae05b2`, `9d6f39e` |

---

## sec9 §9.12 status — 10 required + 1 optional changes

| Wave | Change | Status |
|---|---|---|
| 1 | `hippo-ext-vocabulary` | ✅ |
| 1 | `hippo-core-schema` | ✅ |
| 1 | `id-registry-and-uuid-strategy` | ✅ |
| 1 | `process-class` | ✅ |
| 2 | `provenance-as-linkml-class` | ✅ (declaration-only; Decision 9.6.A split) |
| 2 | `provenance-migration` | ✅ (3 commits; decisions 9.6.B–F) |
| 2 | `computed-temporal-fields` | ✅ (decisions 9.7.E–G) |
| 3 | `validation-tiering-clarification` | ✅ (decisions 9.9.D–E) |
| 3 | `typed-client` | ✅ (decisions 9.8.B, 9.8.F, **9.8.H revised**) |
| 3 | `reference-loader-shape` | ⏸️ **Blocked on design discussion** |
| 3 | `generated-rest-surface` | Optional per sec9 itself; deferred |

**sec9 completion: 9/10 required. 90%.**

---

## What today's session changed (2026-04-22 afternoon/transit)

A four-item post-Wave-3 review. Items 1 and 3 resulted in commits; items 2 and 4 were confirmations of the existing state.

### Item 1 — Pydantic generation failure handling (`9ae05b2`)

- **Question:** Hard-fail or degrade-with-warning when `PydanticGenerator` can't serve a schema?
- **User call:** Hard-fail. "The schema is a compulsory contract."
- **Action:** Decision 9.8.H **revised** — `generate_pydantic_models()` raises `TypedClientError` at each of four failure points (generator import, serialization, Pydantic import, exec) with distinct `.case` identifiers. Tests tightened from conditional to unconditional assertions.
- **Effect:** `EntityAccessor.model_class` is guaranteed non-None for every exposed domain class. A schema the generator can't handle fails at `HippoClient.__init__`.

### Item 2 — `EntityAccessor.delete` routing (confirmation)

- **Question:** Route `client.samples.delete(id)` through `HippoClient.delete` or bypass to `storage.delete`?
- **User call:** Keep routing through `HippoClient` (coequal surface per Decision 9.8.D).
- **Action:** None — already the case. Documented.

### Item 3 — `SDK_RESERVED_NAMES` drift guard (`9d6f39e`)

- **Question:** How to prevent drift when `HippoClient` grows new public attributes?
- **User call:** Test-time guard (option C).
- **Action:** New test `TestReservedNamesGuard::test_reserved_set_covers_every_hippoclient_public_attribute` compares `SDK_RESERVED_NAMES` against `dir(HippoClient)`. **Found 9 existing drift gaps** — closed them: `add_validator`, `get_by_external_id`, `list_external_ids`, `register_external_id`, `relationships`, `schema_references`, `search`, `supersede`, `validate`.

### Item 4 — Tautology test (confirmation)

- Already fixed pre-commit on `9a7b5f4` (advisor caught during Wave 3 review). Nothing to do.

---

## 🚧 Open design questions that block `reference-loader-shape`

Per `openspec/changes/reference-loader-shape/proposal.md`, sec9 §9.5 explicitly flagged two questions for discussion. They need your input before the change can land.

### Question 1 — Multi-class loader cardinality

`ReferenceLoader.entity_type` must be multivalued — a single loader commonly populates several classes (ontology loaders are the canonical example). Open:

- **Ordered vs. set cardinality?** Does the list of `entity_type` entries carry load-order semantics, or is it an unordered set?
- **Per-class metadata location?** If the loader wants to carry per-class info (count estimates, dependencies between classes), does that metadata ride alongside each `entity_type` entry (which means the slot is a list of records, not strings), or does it live on separate records (one `ReferenceLoader` instance per class)?

### Question 2 — Referential boundary of `schema_fragment`

A `ReferenceLoader` instance may reference classes declared in its own `schema_fragment`. Those classes don't exist in the merged `SchemaView` until the plugin's fragment is installed. Open:

- **When is the fragment merged?** At plugin registration? At first invocation of the loader? Lazily on access?
- **When is the `ReferenceLoader` instance validated?** Before the fragment merges (circular — it references classes that don't exist yet) or after (but then what's the error surface if validation fails)?
- **What is the error surface if the fragment can't merge, or if the validated instance is rejected?**

Both questions are architectural. Decision-worthy, not mechanical.

---

## Deferred follow-ups (6 items, tracked in decisions log)

All are small-to-medium, no architectural risk. Pointers to the relevant decisions below.

1. **`actor_id` UUID resolution** — Decision 9.6.F. Currently `"unknown"` sentinel fires when callers don't supply an actor. Needs service-layer context passing real agent UUIDs. Half-session of work once you decide how actor context flows through the SDK.

2. **Drop stored `created_at`/`updated_at` columns on `entities`** — `computed-temporal-fields` Phase E. Columns remain as legacy fallback; SDK already computes via `get_temporal`. Needs a migration + audit of any direct readers.

3. **`ValidationFailed` raise-on-write from typed accessors** — `typed-client` task 6.1. Exception class exists; wiring into `EntityAccessor.create/.put/.replace` is additive.

4. **`hippo.models.<namespace>` import surface** — `typed-client` task 2.3. Generated classes are on `accessor.model_class` today; direct-import path is ergonomics polish.

5. **Dedicated `reference_typed_client.md`** — `typed-client` task 9.1. sec9 §9.8 + `tests/core/test_typed_client.py` document the contract today.

6. **Sec6 Provenance spec revision** — `provenance-migration` task 7.3. Light-touch; plan to land whenever sec6 is next touched.

---

## Known-good state for handoff

- **Branch:** `main`
- **Tests:** 898 passed / 7 skipped (non-Postgres-integration)
- **Tip:** `9d6f39e test(hippo): CI guard against SDK_RESERVED_NAMES drift (item 3)`
- **`origin/main` is 21 commits behind `HEAD`**; `git push origin main` when ready

### Verify on arrival in new environment

```bash
cd hippo
uv run pytest tests/ --ignore=tests/integration/test_postgres_adapter.py -q
# expect: 898 passed, 7 skipped
```

---

## Suggested order of pickup in the new environment

1. **Push** the 21 unpushed commits. Run the verification command above.
2. **Read** this file + `design/sec9_progress_2026-04-22_wave3.md`.
3. **Optional triage** — skim `design/sec9_decisions.md` entries 9.6.B through 9.8.H to see what opinionated calls were made recently.
4. **Choose the next scope** from:
   - **(A)** Unblock `reference-loader-shape` — discuss the two questions above, then ~1 session to land. Finishes sec9 to 10/10.
   - **(B)** Knock off deferred follow-ups (1–6 above). Each is half a session; none blocks anything else.
   - **(C)** Start something new — Hippo is production-ready minus `reference-loader-shape`.

My read, carried over from today's review: (A) when you have time to talk through the design questions; (B) as filler; (C) whenever you want.
