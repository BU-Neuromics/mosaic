## Context

The proposal outlines implementing the foundational base validator infrastructure for Hippo's write validation system. This includes creating an abstract base class (WriteValidator), WriteOperation dataclass, and ValidationResult dataclass. The current codebase has no validation infrastructure - this will establish the core patterns for all future validators in the system.

## Goals / Non-Goals

**Goals:**
- Create WriteValidator ABC with abstract validate method
- Implement WriteOperation dataclass to represent write operations
- Implement ValidationResult dataclass for validation outcomes
- Establish clear patterns for concrete validator implementation

**Non-Goals:**
- Implementing any specific concrete validators (handled in follow-up changes)
- Integration with HTTP transport layer (future work)
- Database persistence concerns (handled by storage adapters)

## Decisions

1. **Dataclasses over Pydantic/attrs**: Using dataclasses for simple data structures. Decision: Native Python dataclasses provide the simplest path with minimal dependencies and no runtime overhead.

2. **ABC over Protocol**: Using ABC for WriteValidator. Decision: ABC provides clearer enforcement of interface contract with raise on non-implementation, appropriate for base class pattern.

3. **Errors as list of strings**: ValidationResult.errors is `list[str]`. Decision: Simple string errors are sufficient for MVP; can evolve to structured error objects later.

4. **Separate result objects**: ValidationResult is separate from exceptions. Decision: Validation is a normal operation returning results, not an exceptional condition - enables batch validation patterns.

## Risks / Trade-offs

- **Risk**: Validation patterns may not match real-world requirements → **Mitigation**: Keep implementation minimal and extensible; iterate based on concrete validator needs
- **Risk**: Type checking complexity → **Mitigation**: Use simple type hints, avoid complex generics for initial version

## Migration Plan

1. Create the base classes in `hippo/core/validation/`
2. Write unit tests for all three components
3. No migration needed - pure addition of new code

## Open Questions

- Should WriteValidator support async validate method for future HTTP transport integration?
- What's the expected pattern for validators to access schema/config?