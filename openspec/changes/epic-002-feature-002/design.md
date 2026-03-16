## Context

The Hippo Metadata Tracking Service needs to generate SQLite DDL from SchemaConfig definitions. This enables dynamic schema creation and migration for the SQLite storage adapter. The SchemaConfig defines entities, fields, relationships, and inheritance strategies that must be translated into valid SQLite CREATE TABLE statements.

Current state: SchemaConfig exists as the in-memory configuration schema. The storage adapter layer needs a DDL generator to materialize this configuration into actual database tables.

## Goals / Non-Goals

**Goals:**
- Generate valid SQLite CREATE TABLE statements from SchemaConfig entities
- Support polymorphic class-table inheritance with proper foreign key relationships
- Generate tables in correct dependency order to maintain referential integrity
- Support all constraint types: PRIMARY KEY, FOREIGN KEY, UNIQUE
- Support DEFAULT values, INDEX declarations, and SQLite-appropriate column types for datetime/boolean

**Non-Goals:**
- PostgreSQL or other database DDL generation (separate future capability)
- Migration DDL (ALTER TABLE for schema evolution - separate capability)
- Data migration or copy operations

## Decisions

1. **Polymorphic inheritance strategy**: Use class-table inheritance where child tables contain only their additional fields plus a foreign key to the parent table. This is appropriate for SQLite's foreign key support and avoids data duplication.

2. **Column type mapping**: Map datetime fields to TEXT (SQLite's datetime storage format) and boolean fields to INTEGER (SQLite has no native boolean). This follows SQLite best practices.

3. **Index generation**: Create partial indexes scoped to `is_available = true` for performance on filtered queries, consistent with the relational storage mapping spec.

4. **Constraint ordering**: Generate tables in topological order based on foreign key dependencies to satisfy SQLite's foreign key constraints.

## Risks / Trade-offs

- **Risk**: SQLite's type affinity may cause issues with strict type checking → Mitigation: Use TEXT for datetime to ensure string comparison works correctly
- **Risk**: Class-table inheritance requires multiple joins for polymorphic queries → Mitigation: Document query patterns; consider denormalization for read-heavy use cases
- **Trade-off**: Single DDL generation pass vs. iterative - choose single pass for simplicity, but may need revisit for complex circular dependencies
