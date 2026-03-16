# EntityStore ABC Implementation - Technical Design

## Context

The Hippo metadata tracking service needs a SQLite storage adapter. This change implements the base `EntityStore` Abstract Base Class (ABC) that defines the interface for all storage adapters. The ABC will provide method signatures for CRUD operations, search functionality, and provenance tracking that any concrete adapter (SQLite, PostgreSQL, etc.) can implement.

Current state: The SDK architecture defines `EntityStore` as the base interface, but no abstract base class exists with method signatures.

## Goals / Non-Goals

**Goals:**
- Define `EntityStore` ABC with abstract method signatures for CRUD operations
- Define search method signatures (find, findAll, findBy)
- Define provenance tracking method signatures
- Ensure type hints and return types are properly defined
- Make the ABC concrete enough for adapters to implement consistently

**Non-Goals:**
- Implementing any concrete adapter (SQLite, PostgreSQL)
- Database schema design
- Query optimization strategies
- Connection pooling or transaction management details

## Decisions

1. **ABC over Protocol**: Use `abc.ABC` instead of `typing.Protocol` because:
   - Enforces implementation via `@abstractmethod` decorator
   - Clear contract that adapters MUST implement all methods
   - Better IDE support and error detection at class definition time

2. **Generic Type Parameters**: Use Python generics for entity types:
   - `EntityStore[T: Entity]` where T is the entity class
   - Allows type-safe CRUD operations returning the correct entity type

3. **Provenance as Separate Methods**: Rather than mixing provenance into CRUD:
   - Explicit `track_creation`, `track_update`, `track_deletion` methods
   - Adapters can implement provenance logging independently
   - Follows separation of concerns principle

4. **Return Type for Searches**: Use `Iterator[T]` for search methods:
   - Memory efficient for large result sets
   - Allows lazy evaluation
   - Adapters can return generators or iterators

## Risks / Trade-offs

- **Risk**: Method signature changes later may break adapter implementations
  - **Mitigation**: Version the ABC interface; document backward compatibility policy

- **Risk**: Generic type handling may be complex for some adapters
  - **Mitigation**: Provide base implementation for common patterns; document type usage

- **Risk**: Provenance methods may need different signatures per adapter
  - **Mitigation**: Keep signatures minimal (entity + metadata dict); let adapters handle storage

## Open Questions

- Should EntityStore ABC include connection management methods?
- Should we provide some default implementations for common patterns?
- What's the versioning strategy for the ABC interface?
