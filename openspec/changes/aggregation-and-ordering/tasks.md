# Tasks — `aggregation-and-ordering`

Tracking issue: BU-Neuromics/mosaic#156

> Design-only at this stage: ADR-0007 is Proposed (#154). Do not start implementation tasks
> until the ADR is ratified and the increment is scheduled.

## 0. Design gate

- [ ] 0.1 ADR-0007 ratified (Status → Accepted; #154 closed with a link to the record).
- [ ] 0.2 Temporal-ordering stance chosen (provenance-summary path with documented cost vs.
  omit from `order_by` in increment 1) and recorded in ADR-0007.
- [ ] 0.3 As-of aggregation stance for increment 1 chosen (documented Python-path compute vs.
  coded error).

## 1. Pushdown + count mode (increment 1)

- [ ] 1.1 `Query` carries `limit`/`offset`/`order_by`; SQLite `_find_per_class` and Postgres
  `find` apply them in SQL; Python paging in `QueryService` demoted to fallback.
- [ ] 1.2 `limit=0` → zero rows preserved end to end (#130), with tests at SDK, REST, and
  GraphQL layers.
- [ ] 1.3 Filtered count on both adapters (`COUNT(*)` under identical predicate +
  `is_available = 1`); SDK count API; `Page.total` resolved from it; no-hydration assertion.
- [ ] 1.4 Parity tests: identical totals/pages on SQLite and Postgres.

## 2. Facet counts + min/max (increment 2)

- [ ] 2.1 `facet_counts(entity_type, field, filters)` on both adapters (GROUP BY column /
  JSONB key), availability-consistent; SDK API + GraphQL `facetCounts(field, where)`.
- [ ] 2.2 Min/max per numeric/date slot under a filter (Postgres via the shared per-range
  cast helper); SDK + GraphQL exposure.
- [ ] 2.3 Availability-consistency tests: seeded unavailable entities never appear in any
  aggregate; aggregates equal what the list surface shows.
- [ ] 2.4 Coded errors for unaggregatable fields (relationship-backed multivalued refs,
  unknown fields) extending the #149 discipline.

## 3. order_by (increment 3)

- [ ] 3.1 Generated per-type `order_by` enum from `filterable_slot_names()` + direction
  argument on list queries; SQL `ORDER BY` pushdown on both adapters with stable
  tie-breaking.
- [ ] 3.2 Computed temporal fields handled per the 0.2 decision — never a raw column sort.
- [ ] 3.3 Parity tests for ordering, including numeric/date slots on Postgres JSONB (casts).

## 4. Docs

- [ ] 4.1 sec4 §4.7 + `docs/graphql.md`: aggregation/ordering surface documented, including
  the availability-consistency guarantee and temporal-ordering semantics.
- [ ] 4.2 `design/INDEX.md` Open Questions row updated on ship.
