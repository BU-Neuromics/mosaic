# Handoff: tag v0.10.0 and v0.10.1 (releases missing tags)

## Why this exists

Issue #90 was fixed and released as **v0.10.1**. In the course of that work we
found that **neither v0.10.0 nor v0.10.1 was ever git-tagged** — the newest tag
on the remote is `v0.9.0`, even though both release-bump PRs (#88, #92) merged
to `main`. The session that discovered this had push access **scoped to the
`claude/issue-90-wun2mm` branch only**, so `git push origin <tag>` returned
HTTP 403 (ref-level authorization denial — not a network/egress issue). Tags
could not be created from that session, and the GitHub integration exposed no
tag/release-creation tool.

**Pick this up in a session with tag-push rights (or do it locally / via the
GitHub web UI) and delete this file when done.**

## What to do

Tags in this repo are **lightweight** (a plain ref to the release commit — see
`v0.7.0`/`v0.8.0`/`v0.9.0`, all `objecttype=commit`), so match that:

```bash
git fetch origin
git tag v0.10.0 0ed1344    # chore(release): v0.10.0 (#88)
git tag v0.10.1 ca7557a    # chore(release): v0.10.1 (#92)
git push origin v0.10.0 v0.10.1
```

Target commits (verify with `git log --oneline`):

| Tag       | Commit    | Commit subject                     |
|-----------|-----------|------------------------------------|
| `v0.10.0` | `0ed1344` | `chore(release): v0.10.0 (#88)`    |
| `v0.10.1` | `ca7557a` | `chore(release): v0.10.1 (#92)`    |

> Note: `0ed1344`/`ca7557a` are the abbreviated SHAs as of this handoff on
> `main`. If history was rewritten since, re-resolve by locating the
> `chore(release): v0.10.x` merge commits on `main`.

Alternatively, create them on GitHub: **Releases → “Draft a new release” →**
pick the tag name, set the target to the commit above, and paste the release
notes below.

## Release notes (ready to paste)

The full source of truth is `CHANGELOG.md`. GitHub-release-formatted notes for
each version are below.

### v0.10.1 — Schema-driven inline value types

Patch release fixing an ingest data-loss bug: inline value-type objects
(identifier-less LinkML classes used as a slot range) were reified into their
own table with a synthetic FK that ingest never populated, so the value was
dropped silently. Value-type detection is now **schema-driven** — any
identifier-less, non-tree-root class is stored inline as JSON TEXT, exactly as
the built-in `ExternalReference` already was.

**Fixed**

- **Inlined value-type objects (identifier-less LinkML classes) no longer
  silently dropped on ingest (#90).** Value-type detection is now schema-driven
  rather than a hardcoded allowlist of one class (`ExternalReference`): any
  non-tree-root class with no identifier slot is treated as an inline value
  type — stored as one JSON TEXT column on the owning entity, never reified
  into its own table with a synthetic FK. Domain value objects such as
  `Mass`/`Volume`/`Concentration` (identifier-less subclasses of an abstract
  `Quantity`) now round-trip exactly as `ExternalReference` does; previously
  `hippo migrate` gave them their own table, `hippo ingest` could not populate
  the resulting `_id` FK from the inline dict, and the value vanished while
  ingest reported `errors=0`. New `SchemaRegistry.value_type_classes()` /
  `is_value_type()` expose the schema-driven set.

Full changelog: https://github.com/BU-Neuromics/hippo/compare/v0.10.0...v0.10.1

### v0.10.0 — Graph-level as-of reconstruction + batch unit-of-work + polymorphic ingest

This release adds **graph-level / query-spanning as-of reconstruction**
(time-travel queries over the whole subgraph, ADR-0001) and a **batch
unit-of-work** (whole-set validation + atomic multi-entity writes, #84), and
fixes two ingest data-loss bugs (multivalued slots #79, polymorphic tree-root
collections #80).

> ⚠️ **Behavior change (#80).** `hippo ingest` no longer silently downcasts a
> subtype instance to a polymorphic base that declares no `designates_type`
> discriminator — it now raises an actionable error instead of dropping the
> subtype's fields. Bundles that previously "succeeded" by discarding those
> fields will now error; add a `designates_type` slot or ingest under the
> concrete-subclass accessor (see `docs/polymorphic-ingest.md`).

**Added**

- **Graph-level / query-spanning as-of reconstruction (ADR-0001, sec6 §6.8;
  #71, increments #73–#77).** Queries can be evaluated as the graph stood at a
  transaction-time `T`, reconstructed from the append-only provenance log (no
  materialized snapshots; transaction-time only, valid-time deferred).
  `HippoClient.query(as_of=...)` reconstructs the matching entity set as of `T`
  and binds the computed temporal fields to `T`;
  `client.relationships.traverse(..., as_of=T)` walks only edges live at `T`,
  replayed from `relationship_add`/`remove` events. Exposed additively on the
  read transports — REST `GET /entities?as_of=<ISO-8601>` and GraphQL
  `asOf: String` on generated list queries (omitted = current state). Backed by
  a new `idx_ProvenanceRecord_type_timestamp` index, with SQLite + PostgreSQL
  parity.

- **Batch unit-of-work: whole-set validation + atomic multi-entity write (#84,
  increments #85–#87).** Commit a set of related entities all-or-nothing, or
  dry-run validate the whole set first. `HippoClient.validate_batch(operations,
  *, assign_ids=True)` runs the standard per-entity pipeline (LinkML → CEL →
  Python) over every operation and aggregates per-entity outcomes (not
  fail-fast), writing nothing. `HippoClient.batch_put(operations, *,
  relationships=None, dry_run=False)` assigns real ids up front, validates the
  whole set, and wraps all entity writes — then relationships — in one
  `staged_transaction()` so the group commits or rolls back together;
  intra-batch relationship forward references resolve naturally. Exposed over
  the transports: REST `POST /ingest/validate` and `POST /ingest/batch`;
  GraphQL `validateBatch` / `ingestBatch` mutations with tier-annotated failure
  types.

**Fixed**

- **Multivalued slots no longer silently dropped on ingest (#79 / ADR-0002).**
  `HippoClient.put` — and therefore `hippo ingest` — previously discarded any
  multivalued slot with no error, because multivalued slots get no per-class
  column and the DDL generator filters out LinkML's linktables. Two storage
  rules now close the gap, both materialized inside the entity-write
  transaction: (1) a multivalued slot whose range is an entity class persists
  as relationships keyed by the slot name — visible to
  `find_relationships`/`traverse` and as-of edge replay — and is hydrated back
  into `entity["data"][slot]` on `get`/`query`; (2) a multivalued slot whose
  range is a scalar/enum stores inline as a single JSON TEXT column. SQLite
  backend; PostgreSQL parity is a follow-up.

- **Polymorphic tree-root collections now ingest with subtype dispatch (#80 /
  ADR-0003).** `hippo ingest` previously skipped abstract bases when building
  the bundle (a collection ranged on an abstract base had no accessor and
  hard-failed validation) and ignored the `designates_type` discriminator (an
  instance under a base-class accessor was silently stored as the base,
  dropping subclass fields). Now an abstract class declaring a `designates_type`
  slot gets a base-ranged tree-root accessor, and ingest dispatches each
  instance to the concrete subclass its discriminator names. A polymorphic base
  with no `designates_type` slot no longer downcasts a subtype to the base — it
  raises an actionable error naming the dropped fields, the valid subclasses,
  and the fix (new guide at `docs/polymorphic-ingest.md`). **Behavior change:**
  bundles that previously "succeeded" by discarding subtype fields now error.

Full changelog: https://github.com/BU-Neuromics/hippo/compare/v0.9.0...v0.10.0

## Cleanup

Once both tags are pushed (and releases created, if you want them), delete this
file:

```bash
git rm HANDOFF-release-tags.md && git commit -m "chore: remove release-tag handoff (tags pushed)"
```
