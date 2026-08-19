# Tasks — `heterogeneous-roots`

Tracking issue: BU-Neuromics/mosaic#158

> Design-only at this stage. Implementation to be scheduled; sequence after (or with)
> `search-composition` so `searchAll` reuses the composed search path.

## 0. Design gate

- [ ] 0.1 Single-valued-edge decision confirmed: union column edges into traversal
  (preferred) vs. loudly-documented stopgap with `edgeSources` disclosure.
- [ ] 0.2 asOf × column-edge stance pinned (per-slot provenance reconstruction vs. coded
  out-of-scope notice) — never a silently partial temporal graph.
- [ ] 0.3 Rank-merge strategy for `searchAll` across classes decided (bm25 scores are
  per-index; define cross-class comparability or per-class quotas).

## 1. `searchAll`

- [ ] 1.1 SDK `search_all(q, limit)` fanning across FTS-indexed classes via the composed
  search path (`search-composition`), merged per 0.3.
- [ ] 1.2 GraphQL `searchAll(q, limit): [SearchHit]` envelope (`entityId`, `entityType`,
  `score`, `data`, temporal fields) with SDL descriptions.
- [ ] 1.3 Batched materialization by type (no per-hit reads; instrumented test).
- [ ] 1.4 Availability parity with list queries; both adapters.

## 2. `neighbors`

- [ ] 2.1 SDK neighborhood API wrapping `RelationshipManager.traverse` (depth-bounded BFS;
  existing as-of variant) returning nodes + edges.
- [ ] 2.2 Column-edge union per 0.1: forward single-valued reference slots read off the
  frontier; reverse edges via schema-driven FK queries (`SlotModel`-derived, no domain
  nouns).
- [ ] 2.3 Batched node materialization by type (the `get_entity_loader` pattern), never
  get-per-node (instrumented test).
- [ ] 2.4 GraphQL `neighbors(id, depth, asOf)` root returning the
  `{nodes, edges {source, target, type}}` envelope with SDL descriptions.
- [ ] 2.5 The gap test: fixture with a link-table edge AND a column-stored single-valued
  reference on the same entity — both edges present, both adapters.
- [ ] 2.6 asOf behavior per 0.2 (provenance-replayed link edges today; column edges per the
  pinned decision, coded notice if scoped out).

## 3. Docs

- [ ] 3.1 sec4 §4.7 + `docs/graphql.md`: heterogeneous roots documented, including the
  envelope-over-union posture (ADR-0005) and the edge-coverage guarantee.
- [ ] 3.2 Changelog entries; note the union/interface root remains future work (its own ADR
  if pursued).
