## ADDED Requirements

### Requirement: DDL generator creates table from single entity
Given a SchemaConfig with a single entity is defined, when the DDL generator processes it, then a correct SQLite table creation statement SHALL be generated for that entity.

#### Scenario: Single entity table generation
- **WHEN** SchemaConfig contains one entity with name "Sample" and fields: id (uuid), name (string), is_available (boolean)
- **THEN** DDL generator outputs: CREATE TABLE samples (id TEXT PRIMARY KEY, is_available INTEGER NOT NULL DEFAULT 1, name TEXT)

### Requirement: DDL generator supports polymorphic class-table inheritance
Given a SchemaConfig with polymorphic inheritance strategy specified as class-table, when the schema generator runs, then appropriate class-table inheritance tables SHALL be created with proper foreign key relationships to parent tables.

#### Scenario: Parent and child entity with class-table inheritance
- **WHEN** SchemaConfig has entity "Container" (parent) with fields: id, name, and entity "Tube" (child) with inheritance strategy class-table, fields: id, color
- **THEN** DDL generator outputs: CREATE TABLE containers (id TEXT PRIMARY KEY, is_available INTEGER NOT NULL DEFAULT 1, name TEXT) and CREATE TABLE tubes (id TEXT PRIMARY KEY, container_id TEXT NOT NULL, color TEXT, FOREIGN KEY (id) REFERENCES containers(id), FOREIGN KEY (container_id) REFERENCES containers(id))

### Requirement: DDL generator creates tables in dependency order
Given a SchemaConfig with multiple related entities exists, when the schema generator runs, then all tables SHALL be created in correct dependency order to maintain referential integrity.

#### Scenario: Entities with foreign key dependencies
- **WHEN** SchemaConfig has entity "Project" with no dependencies and entity "Sample" with foreign key to Project
- **THEN** DDL generator outputs tables in order: first CREATE TABLE projects, then CREATE TABLE samples (referencing projects)

### Requirement: DDL generator includes primary key constraints
Given a SchemaConfig with an entity having primary key constraints, when the DDL generator processes it, then SQLite table creation statements SHALL include appropriate PRIMARY KEY declarations.

#### Scenario: Entity with primary key
- **WHEN** SchemaConfig defines entity "Sample" with id field marked as primary_key: true
- **THEN** DDL output includes "id TEXT PRIMARY KEY"

### Requirement: DDL generator includes foreign key constraints
Given a SchemaConfig with an entity having foreign key relationships, when the DDL generator processes it, then SQLite table creation statements SHALL include appropriate FOREIGN KEY declarations.

#### Scenario: Entity with foreign key reference
- **WHEN** SchemaConfig defines entity "Sample" with field "project_id" referencing entity "Project"
- **THEN** DDL output includes "FOREIGN KEY (project_id) REFERENCES projects(id)"

### Requirement: DDL generator includes unique constraints
Given a SchemaConfig with an entity having unique constraints, when the DDL generator processes it, then SQLite table creation statements SHALL include appropriate UNIQUE declarations.

#### Scenario: Entity with unique field
- **WHEN** SchemaConfig defines entity "Sample" with field "barcode" marked as unique: true
- **THEN** DDL output includes "barcode TEXT UNIQUE"

### Requirement: DDL generator includes default values
Given a SchemaConfig with an entity having default values for columns, when the DDL generator processes it, then SQLite table creation statements SHALL include appropriate DEFAULT declarations.

#### Scenario: Entity with default value
- **WHEN** SchemaConfig defines entity "Sample" with field "status" having default: "pending"
- **THEN** DDL output includes "status TEXT DEFAULT 'pending'"

### Requirement: DDL generator creates index declarations
Given a SchemaConfig with an entity having indexed columns, when the DDL generator processes it, then SQLite table creation statements SHALL include appropriate INDEX declarations.

#### Scenario: Entity with indexed field
- **WHEN** SchemaConfig defines entity "Sample" with field "created_at" marked as indexed: true
- **THEN** DDL output includes "INDEX idx_samples_created_at (created_at) WHERE is_available = 1"

### Requirement: DDL generator handles datetime field types
Given a SchemaConfig with an entity containing datetime fields, when the DDL generator processes it, then SQLite table creation statements SHALL correctly define datetime column types.

#### Scenario: Entity with datetime field
- **WHEN** SchemaConfig defines entity "Sample" with field "created_at" of type datetime
- **THEN** DDL output includes "created_at TEXT" (SQLite TEXT for ISO8601 datetime)

### Requirement: DDL generator handles boolean field types
Given a SchemaConfig with an entity containing boolean fields, when the DDL generator processes it, then SQLite table creation statements SHALL correctly define boolean column types.

#### Scenario: Entity with boolean field
- **WHEN** SchemaConfig defines entity "Sample" with field "is_active" of type boolean
- **THEN** DDL output includes "is_active INTEGER" (SQLite uses INTEGER for booleans)
