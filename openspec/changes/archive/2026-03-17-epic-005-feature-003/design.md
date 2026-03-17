## Context

The Hippo system uses CEL (Common Expression Language) for validation rules defined in `validators.yaml`. Currently, the `ValidationContext` class in `src/hippo/core/validators/context.py` provides a basic context for CEL evaluation by merging entity data with existing entity data and extra variables.

This change enhances the context construction to support:
- **Entity maps**: Multiple sources of entity data to merge
- **Expanded fields**: Dot-notation field expansion (e.g., `user.profile.name`)
- **Type coercion**: Automatic type conversion between strings, numbers, and booleans
- **Missing field handling**: Default values or nulls for required fields
- **Precedence rules**: Last-map-wins for conflicting fields
- **Nested object merging**: Recursive deep merge for nested objects

## Goals / Non-Goals

**Goals:**
- Implement context construction that merges multiple entity maps with proper precedence
- Add type coercion support for string→number, number→boolean, string→boolean, number→string
- Handle missing fields with configurable default values
- Support deep merging of nested objects while maintaining type integrity

**Non-Goals:**
- Changes to CEL expression parsing or evaluation logic (already handled by epic-005-feature-001)
- Changes to the validators.yaml schema format
- Changes to write validation workflow beyond context construction

## Decisions

1. **Type coercion precedence**: Define an explicit precedence order for type conflicts (string > number > boolean > null). This ensures deterministic behavior when merging fields with different types from different sources.

2. **Merge strategy**: Last map wins for scalar values, deep merge for nested objects. This aligns with common merge semantics and provides predictable results.

3. **Field expansion**: Support dot-notation for expanding nested fields into the context (e.g., `user.profile.name` → `{"user": {"profile": {"name": ...}}}`).

4. **Default values**: Use `null` as the default for missing fields rather than raising errors, allowing CEL expressions to handle missing fields gracefully.

## Risks / Trade-offs

- **Risk**: Type coercion could introduce unexpected behavior if coercion rules don't match user expectations.
  - **Mitigation**: Document coercion rules clearly and provide configuration options.

- **Risk**: Deep merging nested objects could be performance-intensive for deeply nested structures.
  - **Mitigation**: Use iterative approach rather than recursive to avoid stack overflow on very deep structures.

- **Risk**: Implicit type coercion could mask type mismatches in validation rules.
  - **Mitigation**: Log warnings when coercion occurs so users can identify potential issues.

## Migration Plan

This change is additive - it extends existing functionality without breaking existing behavior:
1. Existing `ValidationContext` API remains compatible
2. New constructor parameters are optional with sensible defaults
3. Existing tests continue to pass
4. New functionality is opt-in via new parameters

## Open Questions

- Should type coercion be configurable (enable/disable per field or globally)?
- Should there be a maximum depth for nested object expansion/merging?
