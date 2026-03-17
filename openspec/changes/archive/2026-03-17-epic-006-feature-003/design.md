## Context

The Hippo service currently lacks request-level authentication context. We need to implement authentication middleware to extract actor identification from incoming requests via the X-Hippo-Actor header. This enables tracking which user/system initiated requests for auditing and access control purposes.

**Current State:**
- No authentication middleware exists in Hippo
- Requests have no actor context attached

**Constraints:**
- Medium complexity implementation
- Must integrate with existing FastAPI-based transport layer
- Should follow the SDK-first principle (business logic in SDK, thin wrappers for transport)

## Goals / Non-Goals

**Goals:**
- Implement AuthMiddleware ABC (Abstract Base Class) in the Core SDK
- Implement PassThroughAuthMiddleware stub that extracts X-Hippo-Actor header
- Support three header scenarios: valid format, missing header, invalid format
- Integrate with FastAPI transport layer

**Non-Goals:**
- JWT/OAuth token validation (future capability)
- Role-based access control (future capability)
- Integration with external identity providers (future)
- Session management (future)

## Decisions

1. **ABC-based middleware design**: Create `AuthMiddleware` as an Abstract Base Class in `hippo/core/middleware.py` to allow future implementations (JWT, OAuth, etc.) while providing the PassThrough stub now.
   - *Alternative*: Direct implementation without ABC - rejected because it would require refactoring when adding new auth types.

2. **Header-based actor extraction**: Use X-Hippo-Actor header with format "actor:<identifier>" as the initial authentication mechanism.
   - *Alternative*: Query parameter - rejected due to security concerns (logging, caching).
   - *Alternative*: Bearer token - deferred to future JWT implementation.

3. **Single header processing**: When multiple X-Hippo-Actor headers are present, use the first value.
   - *Alternative*: Reject multiple headers - rejected to maintain backward compatibility with HTTP semantics where multiple headers are valid.

4. **SDK-first implementation**: Middleware logic lives in Core SDK, FastAPI transport layer wraps it.
   - *Alternative*: FastAPI-native middleware - rejected per SDK-first principle.

## Risks / Trade-offs

- **Risk**: Actor header can be easily spoofed since it's not validated.
  - *Mitigation*: This is a stub implementation. Future auth types (JWT) will add validation. Current use case is for internal service-to-service communication with implicit trust.

- **Risk**: Empty identifier after "actor:" could cause downstream issues.
  - *Mitigation*: Return 401 error as specified in acceptance criteria.

- **Risk**: No middleware ordering specified in FastAPI.
  - *Mitigation*: Document that AuthMiddleware should be registered first in the middleware stack.

## Migration Plan

1. Add `AuthMiddleware` ABC and `PassThroughAuthMiddleware` to `hippo/core/middleware.py`
2. Add middleware registration in FastAPI app at `hippo/serve/app.py`
3. No database migration required
4. Rollback: Remove middleware registration; system continues without actor context

## Open Questions

- Should the middleware log failed authentication attempts? (Deferred to logging infrastructure work)
- What is the expected identifier format? (Currently any non-empty string after "actor:")
