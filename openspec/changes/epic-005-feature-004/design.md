## Context

Hippo currently lacks built-in preset validators for common validation patterns. Users must implement these validation patterns manually in their schema definitions. This change adds five built-in presets that cover the most frequently needed validation scenarios.

The presets will be implemented as part of the Core SDK's validation system, extending the existing preset infrastructure.

## Goals / Non-Goals

**Goals:**
- Implement five built-in presets: ref_check, count_constraint, immutable_field, field_required_if, no_self_ref
- Ensure each preset follows the existing preset architecture pattern
- Provide clear error messages for each validation failure type
- Integrate presets into the schema compilation workflow

**Non-Goals:**
- UI/API changes for preset management (future work)
- Runtime preset creation (future work)
- Preset customization/extensibility beyond configuration parameters

## Decisions

1. **Configuration-based presets**: Each preset accepts configuration via YAML/JSON schema, keeping them declarative and external to core logic.
2. **Error types**: Each preset will have dedicated error types (ReferenceConstraintViolation, CountConstraintViolation, ImmutableFieldViolation, FieldRequiredViolation, SelfReferenceViolation).
3. **Validation order**: Presets validate in the order they are defined in the schema.

## Risks / Trade-offs

- **Risk**: Error message consistency across presets
- **Mitigation**: Create a shared error message builder utility

- **Risk**: Breaking existing schemas if preset names conflict
- **Mitigation**: Prefix all built-in presets with namespace (e.g., hippo:ref_check)
