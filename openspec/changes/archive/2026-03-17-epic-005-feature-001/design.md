# CEL Validator Engine Design

## Context

The Hippo Metadata Tracking Service needs a CEL (Common Expression Language) validator engine to evaluate validation rules defined in `validators.yaml`. Currently, Hippo lacks the ability to load and execute CEL-based validation conditions against entity data.

**Current State:**
- `validators.yaml` schema already defined with CEL condition fields
- No CEL validation runtime exists in the codebase
- Validation is limited to basic field-level checks

**Constraints:**
- Must work with existing schema-driven data model
- CEL evaluation must return clear error messages for missing fields
- Must handle malformed CEL syntax gracefully with structured exceptions
- Multiple validator rules must not interfere with each other

## Goals / Non-Goals

**Goals:**
- Implement CEL validator engine that loads `validators.yaml`
- Parse CEL conditions and evaluate them against constructed contexts
- Return structured validation exceptions with line numbers for syntax errors
- Handle multiple validator rules independently without interference

**Non-Goals:**
- Real-time CEL expression compilation/optimization
- Custom CEL function extensions (beyond standard cel-go)
- Integration with external validation services
- Performance benchmarking at this stage

## Decisions

### 1. CEL Library Selection: cel-go
Using Google's cel-go library as the CEL runtime. It's the canonical implementation with excellent performance and full CEL specification support.

**Alternatives considered:**
- cel-python: Would require additional runtime dependency
- Custom parser: Too complex, reinvents well-tested functionality

### 2. Engine Architecture: Separate Validator Module
Creating `hippo/core/validators/` as a separate module with clear responsibilities:
- `engine.py`: Main validator orchestrator
- `conditions.py`: CEL condition parsing
- `context.py`: Validation context construction

**Alternatives considered:**
- Inline validation in entity classes: Would violate separation of concerns
- Service layer approach: Overkill for this use case

### 3. Error Handling Strategy
Structured validation exceptions with:
- `ValidationError` base class
- `CELParseError` for syntax errors (includes line number)
- `CELEvaluationError` for runtime errors (includes field reference)

**Alternatives considered:**
- Return boolean + error string: Loses type safety and structure
- Use generic exceptions: Doesn't provide the specific context needed

### 4. Context Construction Approach
Context built from entity data + optional external parameters. Uses dict-like interface compatible with cel-go's standard context format.

**Alternatives considered:**
- Class-based context: More verbose, less flexible
- JSON directly: Loses type information

## Risks / Trade-offs

- **[Risk] CEL version mismatch** → Mitigation: Pin cel-go to specific version; test against CEL specification compliance
- **[Risk] Large context evaluation slow** → Mitigation: Add optional lazy evaluation; profile before optimization
- **[Risk] Invalid YAML blocks engine startup** → Mitigation: Validate YAML structure at load time, report all errors before CEL parsing

## Migration Plan

1. Create `hippo/core/validators/` module
2. Implement `ValidatorEngine` class with `load()`, `evaluate()`, `validate()` methods
3. Add unit tests for all acceptance criteria
4. Integration test with existing `validators.yaml` schema
5. No rollback needed - pure addition, no existing behavior changed

## Open Questions

- Should validator engine be pluggable for future rule types (not CEL)?
- What's the expected scale of validators per entity type?