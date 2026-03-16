## Context

This change implements REST API routers for the Hippo Metadata Tracking Service. The Hippo system currently has a Core Python SDK (`hippo/core/`) with business logic but lacks a transport layer exposing REST endpoints. The implementation will provide HTTP access to core SDK functionality.

**Current State:**
- Hippo SDK exists with classes: `HippoClient`, `QueryEngine`, `IngestionPipeline`, `ProvenanceManager`, `SchemaConfig`
- No HTTP/REST interface currently exists
- Storage backend uses SQLite (v0.1)

**Stakeholders:**
- Frontend applications needing to query entity metadata
- External systems integrating with Hippo
- Internal services requiring REST access to metadata

## Goals / Non-Goals

**Goals:**
- Implement REST API routers for all core entity operations (entity, history, availability, supersede, relationship, external_id, search, ingest, schema)
- Provide CRUD operations via HTTP endpoints
- Include authentication/authorization for protected endpoints
- Support query parameter filtering for entity searches
- Return proper HTTP status codes and error messages

**Non-Goals:**
- Implementing GraphQL API (future work)
- Adding rate limiting or throttling
- Implementing OAuth/OIDC authentication (basic auth only for v0.1)
- Implementing full-text search capabilities beyond basic filtering

## Decisions

### FastAPI over Flask
**Decision:** Use FastAPI for the REST transport layer.

**Rationale:** FastAPI provides automatic OpenAPI documentation, Pydantic validation, async support, and type safety. More suitable for modern Python applications than Flask.

**Alternatives Considered:**
- Flask: Simpler but lacks built-in validation and OpenAPI support
- Aiohttp: Lower-level, requires more boilerplate

### Router Structure
**Decision:** Create separate router files for each entity type (entity, history, availability, supersede, relationship, external_id, search, ingest, schema).

**Rationale:** Follows the SDK's modular structure, makes the codebase easier to navigate and maintain. Each router maps to a specific SDK capability.

**Alternatives Considered:**
- Single monolithic router: Would become unwieldy as the API grows
- Resource-based grouping: Similar but routers provide better separation

### Error Response Format
**Decision:** Use RFC 7807 Problem Details for HTTP API errors.

**Rationale:** Standardized error format that integrates well with HTTP clients and provides consistent error structure across all endpoints.

## Risks / Trade-offs

**[Risk]** SDK methods may not map 1:1 to REST endpoints
→ **Mitigation:** Some SDK operations may need to be composed or decomposed for REST. Design will favor RESTful patterns and document any non-obvious mappings.

**[Risk]** Authentication implementation may block progress
→ **Mitigation:** Start with basic auth, defer more complex auth schemes to future iterations.

**[Risk]** Query parameter filtering complexity
→ **Mitigation:** Begin with simple exact-match filters; implement advanced filtering (regex, ranges) in future phases.

## Migration Plan

**Deployment:**
1. Deploy REST API as new service/endpoint
2. No database migrations required (SDK handles storage)
3. Clients migrate incrementally to new endpoints

**Rollback:**
- Remove REST API service/endpoint
- Clients revert to SDK usage

## Open Questions

- Should endpoints be versioned (e.g., /api/v1/...) from the start?
- What is the expected authentication mechanism for production deployments?
- Should OpenAPI spec be auto-generated or manually maintained?
