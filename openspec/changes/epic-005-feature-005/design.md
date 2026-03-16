## Context

This change integrates validators into the write path, ensuring that configuration-driven business rules execute with proper expansion and validation. Currently, validators exist in validators.yaml but are not executed during write operations. This design addresses how to integrate validators into the write pipeline.

## Goals / Non-Goals

**Goals:**
- Integrate validators into the write path so they execute during create/update/delete operations
- Load validators dynamically from validators.yaml with proper ordering
- Handle validation failures with proper rollback and detailed error messages
- Support nested rule expansion within validators
- Handle validator dependencies on features 001-004
- Manage external API timeouts as validation errors
- Handle invalid validator configurations gracefully

**Non-Goals:**
- Creating new validators (feature-001 concern)
- Validator UI/management interface
- Validator analytics or reporting
- Real-time validator hot-reload (future enhancement)

## Decisions

1. **Where to integrate validators**: Middle of write pipeline, after input parsing but before database commit
   - Rationale: Validators should validate business rules on fully parsed data, and rollback is simpler before commit
   - Alternative: End of pipeline (rejected - harder to rollback)

2. **Execution order**: Load from validators.yaml in defined order, execute sequentially
   - Rationale: Predictable ordering allows business logic dependencies between validators
   - Alternative: Parallel execution (rejected - complex dependency resolution)

3. **Error handling**: Fail fast on first error, with option for collecting all errors
   - Rationale: Simpler implementation, clearer error messages for users
   - Alternative: Collect all errors (future enhancement for better UX)

4. **Dependency initialization**: Initialize dependent features before validator execution
   - Rationale: Validators may depend on features being available
   - Alternative: Lazy initialization (rejected - adds complexity to each validator)

5. **Context propagation**: Validators can modify context, subsequent validators see updates
   - Rationale: Enables chained validation and data transformation
   - Alternative: Immutable context (rejected - limits validator utility)

## Risks / Trade-offs

- **Risk**: Validators executing before dependent features are ready → Mitigation: Initialize features before validator chain
- **Risk**: Long-running validators blocking writes → Mitigation: Configurable timeouts with timeout errors as validation failures
- **Risk**: Invalid validator config crashes system → Mitigation: Load only valid validators, log warnings for invalid entries
- **Risk**: Validator side effects affecting other operations → Mitigation: Each validator runs in isolation; context is request-scoped

## Migration Plan

1. Add validator execution layer to write pipeline
2. Update validators.yaml schema to support write-path configuration
3. Add validation hook to existing write operations
4. Deploy with validators disabled by default (config flag)
5. Enable incrementally per entity type
6. Monitor validation errors and performance

## Open Questions

- Should validators be entity-type specific or global?
- How to handle validator version upgrades?