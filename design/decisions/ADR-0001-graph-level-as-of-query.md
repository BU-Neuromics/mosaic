# ADR-0001: Graph-level / query-spanning as-of reconstruction

- **Status:** Accepted
- **Date:** 2026-06-17 (ratified; design merged as sec6 §6.8)
- **Deciders:** labadorf, design session
- **Related:** **sec6 §6.8 (the design this ADR drives)**, sec6 §6.4/§6.6/§6.7 (temporal fields, provenance storage, history/`state_at`), sec4 §4.3/§4.7 (REST/GraphQL `as_of`), sec3/sec3b (data model & storage), `docs/data-model.md` (`client.state_at`, history); **Aperture ADR-0023** (data-story reproducibility) + Aperture `instruction-path-model.md` §9 (the requirement origin)

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

## Sub-questions resolved (2026-06-17)

The design that resolves these is **sec6 §6.8 (Graph-Level As-Of Reconstruction)**; summary:

1. **Bitemporality → transaction-time only.** `T` selects the graph as Hippo *recorded* it (the
   provenance `timestamp` axis) — exactly what reproducibility needs. Valid-time is deferred (it
   needs per-fact `valid_from`/`valid_to`, a data-model change). *(§6.8.1)*
2. **Transport expression → a per-field `asOf` argument** (REST `?as_of=`, GraphQL `asOf:
   DateTime`), additive and filter-composable; DataLoader batch/cache keys include `asOf`. A
   request-level default may be layered later as ergonomics. *(§6.8.5)*
3. **Performance → query-time reconstruction on the existing `idx_provenance_entity`** plus one
   covering index `idx_provenance_type_time (entity_type, timestamp, entity_id)` for type-scoped
   set selection. No materialized snapshots (a cache tier only if profiling demands). *(§6.8.4)*
4. **Schema-as-of → additive-only tolerance.** Decode as-of-`T` records under the current model;
   slots added after `T` resolve to defaults. Non-additive change between `T` and now is out of
   scope (flagged, not silently mis-decoded). *(§6.8.3)*
5. **Versioning → decomposed into shippable increments** (§6.8.6), sequenced via OpenSpec after
   the current surface; not a v0.1 commitment.

## Notes / remaining items before ratify

- **Ratified `Accepted` 2026-06-17** after review of the sec6 §6.8 design. Implementation is
  decomposed into 5 increments (§6.8.6), tracked in BU-Neuromics/hippo#71 and sequenced via
  OpenSpec.
- **Reconstruction contract to verify in implementation (§6.8.2):** confirm, per `operation`,
  whether each provenance `patch` is a full post-image (latest-record-≤-`T` suffices) or a sparse
  delta (must replay from `create`). Today's `state_at` takes the latest patch; §6.7 intends
  replay — the first increment reconciles them.
- **Relationship liveness must be provenance-driven** (`relationship_add`/`remove` events), since
  `relationships.is_available` carries no change-timestamp (§6.8.2). Confirm those events capture
  enough to reconstruct edge liveness at `T`.
