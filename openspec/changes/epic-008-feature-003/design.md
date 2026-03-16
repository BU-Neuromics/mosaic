## Context

Hippo supports full-text search on fields declared with `search: fts` in entity schemas. The SQLite adapter implements FTS5 search capabilities. However, there's currently no mechanism to:

1. Declare which search modes an adapter supports
2. Validate at startup that the active adapter supports all search modes declared in the schema
3. Fail fast with a clear error when schema declares unsupported search modes (e.g., `search: embedding`)

This feature adds search capability declaration and startup validation to ensure configuration errors are caught early rather than at query time.

## Goals / Non-Goals

**Goals:**
- Add `search_capabilities()` method to EntityStore ABC returning supported search modes as a set
- Implement `search_capabilities()` in SQLite adapter returning `{"fts"}`
- Add startup validation in HippoClient initialization that validates schema-declared search modes against adapter capabilities
- Raise `SearchCapabilityError` at startup if schema declares unsupported search mode

**Non-Goals:**
- Implementing embedding or synonym search (future features)
- Validating search capabilities for inactive adapters
- Adding search capability validation to migration or runtime queries (only startup)

## Decisions

1. **Return type as `set[str]`**: The `search_capabilities()` method returns a set of supported search mode strings (e.g., `{"fts", "embedding"}`). Using a set allows O(1) lookup during validation.

2. **Startup validation timing**: Validation occurs during HippoClient initialization, after the adapter is instantiated but before any requests are served. This ensures fail-fast behavior.

3. **Search mode string values**: Use `"fts"` as the canonical search mode identifier (not `"fts5"`). The schema validator already normalizes `fts5` to `fts` internally. Adapter implementations return `"fts"` regardless of underlying FTS version.

4. **Inactive adapter handling**: When SQLite adapter is inactive (not configured), no validation occurs. This allows schema definitions to include search modes for future adapters without blocking startup.

## Risks / Trade-offs

- **Risk**: Schema validation happens at every HippoClient init, adding slight startup latency.
  - **Mitigation**: The validation is O(n) where n = number of fields with search declared, typically small. Can be cached if needed.

- **Risk**: Schema may declare `search: fts5` while adapter returns `"fts"`.
  - **Mitigation**: The field validator normalizes both to `"fts"` before storage. Comparison uses normalized values.

## Migration Plan

1. Add `search_capabilities()` abstract method to EntityStore ABC
2. Implement `search_capabilities()` in SQLite adapter
3. Add startup validation in HippoClient or schema initialization
4. No database migration needed (purely in-memory validation)

## Open Questions

- Should validation also occur during `hippo serve` FastAPI startup, or only SDK initialization?
- Should the validation be extensible for future adapters to declare their own capabilities?
