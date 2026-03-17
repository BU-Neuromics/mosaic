## Context

The Hippo REST API (from epic-006-feature-001 and epic-006-feature-002) needs automatic OpenAPI documentation generation. All REST endpoints should be documented and accessible via Swagger UI at `/docs` and the raw OpenAPI schema at `/openapi.json`.

FastAPI has built-in support for OpenAPI schema generation and Swagger UI. This feature enables those endpoints.

## Goals / Non-Goals

**Goals:**
- Enable `/docs` endpoint returning Swagger UI (text/html, HTTP 200)
- Enable `/openapi.json` endpoint returning OpenAPI schema (application/json, HTTP 200)
- Ensure all routers registered via app factory are included in the spec
- Configure Swagger UI with proper API info and grouping

**Non-Goals:**
- Customizing the OpenAPI schema (title, version, description) - future enhancement
- Adding authentication to docs endpoint - future stub
- Customizing Swagger UI theme or styling

## Decisions

1. **Use FastAPI's built-in OpenAPI support**: FastAPI's `openapi_schema` property and `SwaggerUI` integration are mature and sufficient for this feature.

2. **Default endpoint paths**: Use FastAPI defaults (`/docs`, `/openapi.json`) for simplicity. These can be customized later if needed.

3. **Include API info**: Set basic API info (title, version) in the OpenAPI schema for better documentation.

## Risks / Trade-offs

- **Risk**: Docstrings not appearing in spec → **Mitigation**: Use Pydantic models with field descriptions and FastAPI's dependency injection for proper schema generation

## Migration Plan

1. Modify `hippo/api/factory.py` to enable OpenAPI endpoints when creating the app
2. Configure Swagger UI with API information
3. Verify all existing routers appear in the generated spec

## Open Questions

- Should the OpenAPI schema be served at a custom path (e.g., `/api/openapi.json`)?
- What should be the API title and version in the OpenAPI spec?