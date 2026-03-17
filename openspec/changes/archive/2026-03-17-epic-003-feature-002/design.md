## Context

This change implements a Schema Validator Registry and Discovery mechanism for the Hippo SDK. The system needs to support multiple validators that can be discovered via Python entry points, ordered by priority, and executed in a write-path pipeline.

Current state: Validators are likely hardcoded or manually registered. The goal is to enable dynamic validator discovery through entry points, allowing external packages to register validators without modifying core SDK code.

## Goals / Non-Goals

**Goals:**
- Enable validator discovery via Python entry points (`hippo.validators`)
- Implement priority-based ordering system (higher priority executes first)
- Create write-path execution pipeline that runs all validators in priority order
- Support multiple validators executing exactly once per write operation

**Non-Goals:**
- Implementing specific validators (those are provided by external packages)
- Validator result aggregation or rollback mechanisms
- Async validator execution
- Validator configuration/parametrization

## Decisions

1. **Entry point-based discovery** over manual registration
   - Rationale: Allows external packages to add validators without SDK modifications
   - Alternative considered: Decorator-based registration (requires imports)

2. **Priority ordering descending** (higher number = runs first)
   - Rationale: Intuitive for users; priority 10 runs before priority 5
   - Alternative considered: Ascending (rejected as counterintuitive)

3. **Pipeline executes all validators** (fail-fast not required for v1)
   - Rationale: Simpler implementation; validators can handle partial data
   - Alternative considered: Stop on first failure (deferred to future)

4. **Single execute call per validator** per write operation
   - Rationale: Predictable behavior; validators manage their own state
   - Alternative considered: Multiple passes (over-engineered)

## Risks / Trade-offs

- **Entry point caching**: Entry points are discovered at import time. New validators require package reinstall. → Mitigation: Document this in SDK docs
- **Priority conflicts**: Two validators with same priority have undefined order → Mitigation: Use stable sort; document that equal priorities have unspecified order
- **Import-time discovery**: Slows initial import if many validators registered → Mitigation: Lazy loading pattern available for future optimization

## Migration Plan

This is a new feature (no existing behavior to migrate):
1. New `ValidatorRegistry` class discovers validators on initialization
2. New `ValidatorPipeline` class executes validators in order
3. SDK's write operations integrate with pipeline
4. No breaking changes to existing APIs

## Open Questions

- Should validators be re-discovered on each write (for development) or cached?
- What should happen if a validator raises an exception?
