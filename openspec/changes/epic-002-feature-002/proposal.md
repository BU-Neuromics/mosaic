# SQLite Database Schema Generation

## Goal
SQLite Database Schema Generation: Implement DDL generation from SchemaConfig including support for polymorphic class-table inheritance strategy.

## Acceptance Criteria
- Given a SchemaConfig with a single entity is defined, when the DDL generator processes it, then a correct SQLite table creation statement is generated for that entity
- Given a SchemaConfig with polymorphic inheritance strategy specified as class-table, when the schema generator runs, then appropriate class-table inheritance tables are created with proper foreign key relationships to parent tables
- Given a SchemaConfig with multiple related entities exists, when the schema generator runs, then all tables are created in correct dependency order to maintain referential integrity
- Given a SchemaConfig with an entity having primary key constraints, when the DDL generator processes it, then SQLite table creation statements include appropriate PRIMARY KEY declarations
- Given a SchemaConfig with an entity having foreign key relationships, when the DDL generator processes it, then SQLite table creation statements include appropriate FOREIGN KEY declarations
- Given a SchemaConfig with an entity having unique constraints, when the DDL generator processes it, then SQLite table creation statements include appropriate UNIQUE declarations
- Given a SchemaConfig with an entity having default values for columns, when the DDL generator processes it, then SQLite table creation statements include appropriate DEFAULT declarations
- Given a SchemaConfig with an entity having indexed columns, when the DDL generator processes it, then SQLite table creation statements include appropriate INDEX declarations
- Given a SchemaConfig with an entity containing datetime fields, when the DDL generator processes it, then SQLite table creation statements correctly define datetime column types
- Given a SchemaConfig with an entity containing boolean fields, when the DDL generator processes it, then SQLite table creation statements correctly define boolean column types

## Constraints
- Complexity: medium
