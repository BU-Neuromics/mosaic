# Tasks — `actor-context-resolution`

## 1. Core context module

- [x] 1.1 `src/hippo/core/context.py` — `current_actor: ContextVar[Optional[str]]`,
  `get_current_actor()`, `set_actor()`, `with_actor()` context manager.

## 2. Adapter updates

- [x] 2.1 `sqlite_adapter.py` `ProvenanceStore.record()` — insert ContextVar
  lookup (step 3) between the `user_context` shim (step 2) and the `"unknown"`
  sentinel (step 4).
- [x] 2.2 `postgres_adapter.py` `ProvenanceStore.record()` — same change.

## 3. Middleware bridge

- [x] 3.1 `middleware.py` `PassThroughAuthMiddleware.__call__` — call
  `current_actor.set(context.actor_id or None)` at entry; reset via token in
  `try/finally`.

## 4. Tests

- [x] 4.1 `tests/core/test_actor_context.py` — 9 tests covering:
  - ContextVar default, set/restore, nesting, exception recovery
  - ProvenanceStore picks up ContextVar when `actor_id=None`
  - `"unknown"` fallback when no context set
  - Explicit kwarg overrides ContextVar
  - Middleware sets ContextVar per HTTP request
  - No header leaves ContextVar as `None`

## 5. Decision log

- [x] 5.1 Decision 9.6.G added to `design/sec9_decisions.md` — ContextVar
  approach, resolution order, scope note for `track_*` in-memory methods.
