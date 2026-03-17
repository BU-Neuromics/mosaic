# Tier 1 Schema Validation Design

## Context

The Hippo Metadata Tracking Service requires a multi-tier validation system to enforce data quality at different levels of granularity. The Tier 1 Schema Validator is the highest-priority validation layer that enforces foundational constraints: required fields, type validation, enum constraints, and referential integrity.

This validator operates at the schema level, examining incoming write operations against the defined schema configuration (entity types, field definitions, enums, and relationships). It is the first line of defense, ensuring that data conforms to the structural and semantic rules defined in the schema before any persistence occurs.

The validator must produce structured ValidationResult objects that clearly communicate success or failure, including specific error messages with field names, expected types, and reference information for debugging.

## Goals / Non-Goals

**Goals:**
- Validate required fields are present in write operations
- Validate field types match schema definitions (string, number, boolean, timestamp)
- Validate enum values conform to allowed sets
- Validate referenced entity IDs exist in the system
- Support nested object validation for complex field structures
- Produce clear, actionable error messages for validation failures
- Collect multiple validation errors into a single result for efficiency

**Non-Goals:**
- Tier 2+ validation (business logic, cross-entity rules, derived fields)
- Validation for queries/read operations (write-focused)
- Schema introspection or discovery (validation-only)
- User interface for validation errors (API/SDK only)

## Decisions

### 1. ValidationResult Structure
- **Decision**: ValidationResult SHALL contain `is_valid` boolean, `errors` list, and optional `entity_id` for context
- **Rationale**: Simple, machine-parseable format that works across transport layers
- **Alternative**: Separate error type objects per validation category — rejected for complexity

### 2. Error Message Format
- **Decision**: Error messages SHALL follow specific patterns (e.g., "Field 'X' is required", "Expected Y type for field 'Z'")
- **Rationale**: Consistent format enables automated parsing and testing
- **Alternative**: Free-form messages — rejected for test automation requirements

### 3. Validation Timing
- **Decision**: Tier 1 validation runs before any persistence, as part of the IngestionPipeline pre-commit phase
- **Rationale**: Fail-fast prevents invalid data from reaching storage
- **Alternative**: Deferred validation with later reconciliation — rejected for data integrity

### 4. Reference Validation Scope
- **Decision**: Reference validation checks existence in the current schema context only; does not validate cross-schema references
- **Rationale**: Simpler implementation for initial tier; schema composition is future work

### 5. Nested Field Handling
- **Decision**: Dot-notation path format (e.g., "nested.field") for nested field error reporting
- **Rationale**: Standard convention, matches LinkML path format

## Risks / Trade-offs

- **[Risk] Schema compilation timing**: The schema must be compiled to LinkML before Tier 1 validation can run → **Mitigation**: Ensure schema compilation happens in the pipeline before validation phase
- **[Risk] Performance with large payloads**: Validating many fields may be slow → **Mitigation**: Early exit on first error optional; default to collect-all for completeness
- **[Risk] Enum value case sensitivity**: Ambiguous whether enums are case-sensitive → **Mitigation**: Default to case-sensitive; document in schema specification
- **[Risk] Circular relationship validation**: Entity A references B, B references A → **Mitigation**: Reference validation is existence-check only; no recursion depth limits needed

## Migration Plan

This is a new component with no existing behavior to migrate.

1. Implement SchemaValidator class in `hippo/core/validation/`
2. Add `validate()` method to IngestionPipeline pre-commit hook
3. Wire ValidationResult into write operation response
4. Add unit tests for each validation scenario from specs
5. Document API in SDK docstrings

## Open Questions

- Should the validator support validation level configuration (strict vs permissive)?
- How to handle validation of dynamically added fields vs. statically defined fields?
- What is the expected behavior when schema itself is invalid/malformed?