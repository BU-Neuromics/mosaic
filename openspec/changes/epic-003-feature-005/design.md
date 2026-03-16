# Design: Schema Validation Integration Tests

## Context

This change implements integration tests for the schema validation system in Hippo. The validation system ensures that entities conform to their defined schemas before being written to storage. This change adds comprehensive test coverage for all validation scenarios.

**Current State:**
- Schema validation logic exists in the Core SDK (`hippo/core/`)
- Validation covers required fields, foreign key references, data types, and constraints
- No comprehensive integration tests currently exist

**Dependencies:**
- feature-003: Schema definition system
- feature-004: Validation engine implementation

## Goals / Non-Goals

**Goals:**
- Create integration tests covering all validation scenarios
- Test positive cases (valid data passes)
- Test negative cases (invalid data fails with appropriate errors)
- Test integration points between validation and storage

**Non-Goals:**
- Unit tests for individual validation functions (covered elsewhere)
- Performance/load testing
- Schema definition changes

## Decisions

### Test Approach
Use pytest with the existing test infrastructure in the codebase. Tests will use the `HippoClient` API directly to exercise validation logic end-to-end.

### Test Organization
Group tests by validation category:
- Required field validation
- Foreign key reference validation  
- Data type validation
- Constraint validation (length, size)

## Risks / Trade-offs

- **Risk**: Tests may be brittle if error messages change frequently
  - **Mitigation**: Focus tests on error types/codes rather than exact message text

- **Risk**: Integration tests may be slow
  - **Mitigation**: Use in-memory SQLite for fast test execution

## Open Questions

- Should tests be parametrized for all entity types, or just representative samples?
- Should negative test cases use fixtures or inline data?
