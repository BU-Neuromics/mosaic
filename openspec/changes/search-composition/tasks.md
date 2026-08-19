# Tasks — `search-composition`

Tracking issue: BU-Neuromics/mosaic#157

> Design-only at this stage. Implementation to be scheduled; the three defect fixes
> (N+1, missing envelope, slice bug) can ship against the v0.12 surface without waiting on
> ADR-0006/0007 ratification.

## 0. Design gate

- [ ] 0.1 bm25-rank vs. `order_by` precedence confirmed (recommended: rank by default,
  explicit `order_by` overrides) and recorded here + in ADR-0007's notes if it lands first.
- [ ] 0.2 Breaking envelope change (bare list → `Page`) sequenced with a version bump and
  consumer notice.

## 1. Id-set composition in the search service

- [ ] 1.1 `QueryService.search` rewritten: ranked FTS ids → one `find()` call with
  `id IN (…)` composed with caller filters; per-hit `get` loop removed.
- [ ] 1.2 Rank order preserved through composition (re-order the page by FTS rank after
  `find()`, or push rank join down — decide by measurement).
- [ ] 1.3 Postgres search path composes identically (parity tests).
- [ ] 1.4 Availability filtering identical to list queries (unavailable entities never
  surface via search).

## 2. Page envelope + filter arguments on the transports

- [ ] 2.1 GraphQL search twins return the `Page` type (`items/total/limit/offset`);
  resolver-side slicing deleted (kills the `offset >= limit → []` bug).
- [ ] 2.2 Search twins accept `filters:` (and `where:` once `typed-filter-inputs` lands),
  with the coded-error discipline for unknown fields.
- [ ] 2.3 REST search endpoint mirrored to the same envelope/arguments (SDK-first: the SDK
  search API returns `PaginatedResult`).

## 3. Tests & docs

- [ ] 3.1 Regression test: `offset >= limit` returns the correct page; full page-through
  visits every hit once.
- [ ] 3.2 Instrumented no-N+1 assertion (one batched read per page).
- [ ] 3.3 `total` correctness under composed filters, both adapters.
- [ ] 3.4 Changelog BREAKING entry; `docs/graphql.md` + sec4 §4.7 search sections updated.
