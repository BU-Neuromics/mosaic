# ADR-0001: Graph-level / query-spanning as-of reconstruction

- **Status:** Proposed
- **Date:** 2026-06-17
- **Deciders:** labadorf, design session
- **Related:** sec6 (Provenance & Audit), sec4 §4.7 (GraphQL transport), sec3/sec3b (data model & storage), `docs/data-model.md` (`client.state_at`, history); **Aperture ADR-0023** (data-story reproducibility) + Aperture `instruction-path-model.md` §9 (the requirement origin)

## Context

Aperture builds **data stories** — narrated, re-runnable analyses over the domain graph — whose
defining property is **reproducibility**: a story composed today must reproduce *identically*
whenever it is rerun, unless the user explicitly pulls in new data (Aperture ADR-0023). To
deliver that, a story pins a single **as-of watermark** (a timestamp `T`) and every query in the
story must resolve against the graph **as it stood at `T`** — entities, relationships, *and* the
schema version all reconstructed to `T`.

Hippo already owns the substrate for this and is the only component that can: no hard deletes; an
append-only provenance log with `state_snapshot` + `previous_state_hash`; per-entity
reconstruction via `client.state_at(entity_id, T)`; and `schema_version` derived from the
provenance log. **What does not yet exist is a *query-spanning* as-of capability** — "evaluate
this whole subgraph query as the graph stood at `T`." Today's surface reconstructs **one entity
at a time**, and the GraphQL transport (sec4 §4.7) takes equality filters + offset only, with no
temporal parameter and additive-only evolution.

The question: **does Hippo provide graph-level as-of reconstruction as a first-class capability,
and how is the watermark expressed across the SDK and transports?** If it does not, reproducible
data stories are impossible (or get faked in Aperture, in the wrong place).

## Decision

**Hippo will provide graph-level, query-spanning as-of reconstruction as a first-class
capability.** A read may carry an as-of timestamp `T`; when present, the *entire* query —
entity selection, relationship traversal, and the schema/type resolution used to interpret the
result — is evaluated against the graph as it existed at `T`, reconstructed from the provenance
log. The capability is exposed uniformly:

- **SDK** — an as-of parameter on the query/traversal surface (generalizing today's per-entity
  `state_at` to the query engine), returning a consistent point-in-time subgraph.
- **Transports** — the watermark is carried on REST and GraphQL reads (an additive parameter,
  consistent with sec4 §4.7's additive-only discipline), so consumers like Aperture get
  point-in-time reads without composing per-entity reconstructions client-side.

Reads without `T` behave exactly as today (current state). The capability is **read-only** and
changes nothing about the write path or the append-only log; it is a new *view* over data Hippo
already retains.

## Consequences

- **Unblocks Aperture data-story reproducibility** (ADR-0023): a story pins `T` once, replays
  deterministically, and "pull new data" becomes "advance `T`" — all on Hippo-native semantics,
  not an Aperture-side snapshot hack.
- **Extends the platform invariant** that every domain Aperture drives expose a typed,
  introspectable, dry-run-validatable, provenance-tracked — **and time-travelable** —
  representation. Hippo is the reference for "time-travelable."
- **New obligations on Hippo:** the query engine and storage adapters must support point-in-time
  reconstruction over a *set* of entities and their relationships consistently (not N independent
  `state_at` calls); provenance indexes must make this tractable at scale; the transports gain an
  additive temporal parameter and must document its semantics.
- Touches **sec6** (the reconstruction algorithm + indexing), **sec4** (REST/GraphQL parameter),
  and **sec3b** (adapter support + performance). Likely a multi-version effort; this ADR records
  the requirement and direction, not a v0.1 commitment.

## Alternatives considered

- **Snapshot results inside Aperture** (materialize and store query outputs per story). Puts
  reproducibility in the wrong layer, balloons story size, and breaks re-rooting/replay — exactly
  the extensional-state failure Aperture ADR-0022/0023 reject. Rejected: provenance is Hippo's,
  so time-travel belongs in Hippo.
- **Compose per-entity `state_at` client-side.** Cannot reconstruct relationship traversal or
  faceted queries consistently, suffers N+1 and read-skew (different entities reconstructed at
  slightly different moments), and re-implements graph evaluation outside the engine that owns it.
  Rejected.
- **Maintain explicit materialized snapshots / copies of the graph at checkpoints.** Storage
  cost, checkpoint-cadence guesswork, and it duplicates what the append-only provenance log
  already encodes. Rejected: reconstruct from the log on demand.

## Notes / open sub-questions

- **Bitemporality:** is **transaction-time** as-of (when Hippo recorded the fact) sufficient, or
  is **valid-time** (when the fact was true in the world) also needed? The provenance log gives
  transaction-time directly; valid-time would be a larger data-model change. Lead with
  transaction-time.
- **GraphQL expression:** a per-query argument vs. a request-level header vs. a "snapshot handle"
  obtained once and reused — which best fits the additive-only contract and DataLoader batching?
- **Performance:** what provenance indexes / caching make subgraph reconstruction at `T`
  acceptable? Relationship immutability (relationships are append-only) helps.
- **Schema-as-of:** confirm `schema_version` reconstruction at `T` composes cleanly with typed
  decoding when the schema has evolved between `T` and now (additive-only tolerance).
- **Versioning:** scope which Hippo version targets this; the requirement is recorded now,
  driven by Aperture's keystone.
