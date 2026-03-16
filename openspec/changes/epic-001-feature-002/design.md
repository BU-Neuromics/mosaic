# SchemaConfig Pydantic Model Implementation - Design

## Context

This change implements the SchemaConfig Pydantic model and a Hippo DSL YAML parser for the Hippo Metadata Tracking Service. The parser must support base inheritance with cycle detection for schema validation.

### Background
- Hippo uses config-driven relational storage with a graph-shaped API
- Entity types and relationships are defined in YAML/JSON schema
- The system needs to validate schema files and detect circular inheritance in base references

## Goals / Non-Goals

**Goals:**
- Implement SchemaConfig Pydantic model with all necessary fields
- Create YAML parser to load and validate Hippo DSL schema files
- Implement cycle detection for base inheritance (single and multi-schema cycles)
- Provide clear error messages with error codes for validation failures

**Non-Goals:**
- Database persistence layer (future consideration)
- GraphQL transport layer
- External system adapters (STARLIMS, HALO, Donor DB)

## Decisions

1. **Pydantic v2 for SchemaConfig model**
   - Use Pydantic v2 for schema validation and serialization
   - Provides built-in validation, serialization, and JSON Schema generation

2. **YAML parsing with PyYAML + custom validation layer**
   - Use PyYAML for base YAML parsing
   - Add custom validation layer on top for schema-specific rules

3. **Graph-based cycle detection algorithm**
   - Build directed graph of base dependencies
   - Use DFS with visited/recursion stack for cycle detection
   - Track full cycle path for error reporting

4. **Error code schema**
   - `CYCLE_DETECTED`: Circular inheritance in single schema
   - `CIRCULAR_INHERITANCE`: Multi-schema circular inheritance
   - `BASE_NOT_FOUND`: Reference to undefined base schema
   - Field validation errors with clear messages

## Risks / Trade-offs

- **Risk**: Deep inheritance chains (10+ levels) may impact performance
  - **Mitigation**: Add depth limit validation (e.g., max 20 levels)

- **Risk**: Multiple inheritance paths may cause field resolution ambiguity
  - **Mitigation**: Define clear field precedence order (child > parent > grandparent)

- **Risk**: Large schema files may cause memory issues
  - **Mitigation**: Use lazy loading for base schemas

## Migration Plan

1. Implement SchemaConfig Pydantic model
2. Implement YAML parser with validation
3. Add cycle detection algorithm
4. Add comprehensive error handling
5. Write unit tests for all acceptance criteria
6. Integration test with sample schemas

## Open Questions

- Should we support JSON schema files in addition to YAML?
- What is the maximum acceptable inheritance depth?
- Should we cache parsed schemas for performance?
