# Generated REST Surface

**Status:** Optional, deferred. Per sec9 §9.12, this change is marked
optional and deferred — sec9 completes without it. Included here as a
scaffold for when the typed client demonstrates enough static-surface
value to motivate pushing the pattern to REST.

## Why

After `typed-client`, Hippo's Pydantic classes are generated from the
merged schema. The REST layer today is hand-wrapped FastAPI routes. A
natural next step is to generate REST endpoints and OpenAPI from the
schema too — one less place for schema/code drift.

## What Changes (sketch)

- FastAPI routers generated per class: `POST /entities/{class}`,
  `GET /entities/{class}/{id}`, `PUT /entities/{class}/{id}`, etc.
- OpenAPI schema derived from the generated Pydantic classes (FastAPI
  does this automatically).
- Hand-written endpoints migrated to the generated path or explicitly
  flagged as "retained custom" with rationale in `sec9_decisions.md`.

## Capabilities

### New Capabilities

- `generated-rest-surface` — REST endpoints derived from the schema.

### Modified Capabilities

- `hippo-rest-api` — most hand-written routes replaced.

## Dependencies

- **Blocked by:** `typed-client`.

## Acceptance

- REST callers see the same surface (no observable behavior change).
- Maintenance cost of the REST layer measurably drops (removed N
  hand-written route files).
- Full suite green.

## Open Questions

- Which existing hand-written routes must stay bespoke (auth flows,
  bulk-operation endpoints, GA4GH DRS surface, etc.)?
- How do CEL / Python validators' error responses propagate through the
  generated routes?
- OpenAPI naming and versioning conventions.
