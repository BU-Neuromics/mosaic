## Context

The Hippo project needs a FastAPI application factory that:
- Creates FastAPI instances programmatically
- Mounts all routers dynamically
- Provides consistent global error handling for:
  - ValidationError → HTTP 422
  - EntityNotFoundError → HTTP 404
  - Generic Exception → HTTP 500

This is needed to support the transport layer for the REST API (FastAPI `hippo serve`).

## Goals / Non-Goals

**Goals:**
- Create a reusable `create_app()` factory function that returns a FastAPI instance
- Support dynamic router mounting from configuration
- Implement global exception handlers for consistent API error responses
- Handle empty router list gracefully

**Non-Goals:**
- Database connection management (handled by storage adapters)
- Authentication/authorization (future stub)
- GraphQL support (future enhancement)

## Decisions

1. **Factory Pattern**: Use a factory function `create_app(routers: list[APIRouter] = None)` that returns a configured FastAPI instance. This allows flexible app creation and testing.

2. **Error Response Format**: Use Pydantic models for error responses to ensure consistent structure:
   ```python
   class ErrorResponse(BaseModel):
       error: str
       detail: Optional[str] = None
   ```

3. **Exception Mapping**:
   - `ValidationError` (Pydantic) → 422
   - `EntityNotFoundError` (custom) → 404
   - Generic `Exception` → 500 (with logging)

4. **Router Registration**: Accept list of APIRouter instances, default to empty list.

## Risks / Trade-offs

- **Risk**: Generic exception handler masks unexpected errors → **Mitigation**: Log full traceback for 500 errors
- **Risk**: Custom EntityNotFoundError not defined yet → **Mitigation**: Create a simple exception class in the same module

## Migration Plan

1. Create `hippo/api/factory.py` with `create_app()` function
2. Add global exception handlers
3. Export from `hippo/api/__init__.py`
4. Add tests for router mounting and error handling

## Open Questions

- Should the app factory support OpenAPI schema customization?
- What's the preferred naming for the `EntityNotFoundError` exception?
