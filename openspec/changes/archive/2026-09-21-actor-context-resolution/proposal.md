# Actor Context Resolution via ContextVar

## Why

`provenance-migration` (Decision 9.6.F) flagged two known transition-period
fallbacks. This change resolves **Fallback 1**: `ProvenanceStore.record()`
defaulting `actor_id` to the literal string `"unknown"` when callers pass
`None`. Several write paths in `ingestion_service.py` and the SQLite/Postgres
adapters produce `actor_id = "unknown"` rows because they don't have a
mechanism to carry per-request actor context without threading an extra
parameter through every method signature.

## What Changes

### New module: `hippo.core.context`

Exports `current_actor` (`ContextVar[Optional[str]]`), `get_current_actor()`,
`set_actor()`, and `with_actor()` context manager. This is the canonical
location for request-scoped SDK state.

```python
# Direct SDK use
with with_actor("agent-uuid-here"):
    client.create("Sample", {...})

# FastAPI route (actor already set by middleware)
@router.post("/entities")
async def create_entity(request: Request, body: ...) -> ...:
    # current_actor is already set by PassThroughAuthMiddleware
    return client.create(body.entity_type, body.data)
```

### Updated: `ProvenanceStore.record()` (both adapters)

Resolution order for `effective_actor`:

1. Explicit `actor_id=` kwarg
2. Legacy `user_context=` shim (Decision 9.6.B — still accepted)
3. `current_actor.get()` from the ContextVar
4. `"unknown"` sentinel (last resort; satisfies NOT NULL)

### Updated: `PassThroughAuthMiddleware`

Sets `current_actor` from the resolved `X-Hippo-Actor` header value at
request entry. Resets it via token in a `try/finally` block so each async
request is isolated.

## What Does Not Change

- Public write method signatures on `HippoClient` or `IngestionService` — no
  `actor_id` parameter added to `put`, `create`, `update`, `replace`, `delete`.
- `track_creation`, `track_update`, `track_deletion` — in-memory records only,
  no DB write, not part of the 9.6.F sentinel scope.
- The `"unknown"` sentinel itself — retained as a safety net that flags
  unmigrated paths rather than silently dropping provenance records.

## Decision Reference

Decision 9.6.G in `design/sec9_decisions.md`.
