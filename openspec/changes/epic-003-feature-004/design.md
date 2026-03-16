## Context

This design covers the Write Operation Validation Pipeline for the Hippo Metadata Tracking Service. The pipeline ensures all write operations pass through registered validators in sequence before being processed. This is feature-004 of epic-003, building upon features 001-003 which established the core SDK, query engine, and schema configuration.

### Current State
- Core SDK (`hippo/core/`) provides `HippoClient`, `QueryEngine`, `SchemaConfig`
- Validators are registered via configuration but lack a unified execution pipeline
- Write operations can bypass validation through direct storage access
- No centralized way to enforce validation order or capture failure details

### Constraints
- Must integrate with existing `SchemaConfig` for validator registration
- Must work with SQLite v0.1 storage backend (PostgreSQL future)
- Cannot modify existing entity tables' schemas
- Validation failures must be logged with full context for debugging

### Stakeholders
- SDK users (internal BASS platform services)
- Integration teams connecting STARLIMS, HALO, Donor DB

## Goals / Non-Goals

**Goals:**
- Implement a pipeline that executes all registered validators in defined order
- Ensure no bypass paths exist for write operations
- Provide detailed failure messages indicating which rule failed
- Support custom validator logic execution
- Enforce exactly-once execution per validator per operation

**Non-Goals:**
- Replacing existing storage backends
- Implementing specific validation rules (handled by features 001-003)
- Real-time validation monitoring/dashboards
- Cross-service validation coordination

## Decisions

### 1. Pipeline Architecture: Decorator Pattern over Middleware
**Choice:** Use a decorator/wrapper pattern around `HippoClient.write()` rather than a separate pipeline class.

**Rationale:** Minimizes API surface changes, integrates naturally with existing SDK patterns, easier to test in isolation.

**Alternatives Considered:**
- Separate `ValidationPipeline` class: More explicit but requires users to learn new API
- Middleware chain: Common in web frameworks but overkill for SDK use case

### 2. Validator Execution: Sequential with Fail-Fast
**Choice:** Validators execute sequentially in registration order with immediate fail-fast on first failure.

**Rationale:** Simpler to reason about, matches most validation scenarios, provides clear failure points.

**Alternatives Considered:**
- Parallel execution: Complex error handling, harder to determine failure order
- Continue-all: Less efficient, overwhelming error messages

### 3. Failure Reporting: Structured Error with Rule Details
**Choice:** Create `ValidationFailure` exception containing rule ID, message, and context.

**Rationale:** Programmatic access to failure details enables automated retry/handling.

**Alternatives Considered:**
- String-only errors: Simpler but requires parsing for automation
- Multiple exception types: Over-engineered for expected use cases

### 4. Custom Validators: Config-Driven Registration
**Choice:** Register custom validators via `SchemaConfig` YAML/JSON, not code.

**Rationale:** Keeps business logic in configuration as per architecture principles, enables runtime changes.

**Alternatives Considered:**
- Code registration: More flexible but couples logic to implementation
- Plugin system: Over-engineered for current scope

## Risks / Trade-offs

### Risk: Validation Performance Impact
**Description:** Sequential validation adds latency to every write operation.

**Mitigation:** 
- Keep validators lightweight
- Consider async execution for independent validators in future
- Document expected overhead (~5-10ms per validator)

### Risk: Circular Dependencies Between Validators
**Description:** Custom validators might depend on each other creating cycles.

**Mitigation:**
- Validate DAG structure at startup
- Document validator ordering requirements
- Provide clear error on cycle detection

### Risk: Backward Compatibility
**Description:** Adding mandatory validation might break existing code that relied on bypass.

**Mitigation:**
- Provide `bypass_validation` flag (deprecated) for migration period
- Document migration path in release notes
- Default to strict mode in next major version

### Trade-off: Completeness vs. Speed
**Choice:** Fail-fast is simpler but doesn't report all validation errors at once.

**Acceptance:** Most use cases have single-point failures; full report available via re-validation after fixes.

## Migration Plan

### Phase 1: Core Pipeline (this change)
1. Implement `ValidationPipeline` class in `hippo/core/pipeline.py`
2. Add `validate()` method to `HippoClient`
3. Create `ValidationFailure` exception
4. Wire pipeline into write operations

### Phase 2: Configuration Integration
1. Update `SchemaConfig` to load validator definitions
2. Register default validators (feature-001 to 003)
3. Add custom validator support in YAML schema

### Phase 3: Observability
1. Add validation timing metrics
2. Log failure details for debugging
3. Optional: Validation audit trail

### Rollback Strategy
- Keep `bypass_validation` flag available
- Pipeline can be disabled via config if critical issue found
- Storage layer unaffected (validation happens before storage)

## Open Questions

1. **Validation Order Priority:** Should validators have explicit priority numbers or rely on registration order?
   - Current: Registration order (simpler)
   - Alternative: Priority numbers (more control, more complexity)

2. **Cross-Entity Validation:** Should the pipeline support validators that check relationships between multiple entities?
   - Current: Single-entity only
   - Alternative: Relationship validators (future feature)

3. **Retry Logic:** Should failed validations be retried automatically?
   - Current: No (fail-fast)
   - Alternative: Configurable retry with backoff (future feature)
