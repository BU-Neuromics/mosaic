## MODIFIED Requirements

### Requirement: System fields are described conceptually
The system fields table in sec3 §3.2 SHALL list fields by name, type, and behavior — without a "Storage location" column. The table SHALL describe what each field represents to callers, not where it is physically stored. `created_at`, `updated_at`, and `schema_version` SHALL be described as computed fields derived from the provenance system and presented on all entity response objects.

#### Scenario: System fields table has no storage implementation detail
- **WHEN** a reader views the system fields table in sec3
- **THEN** the table contains columns for Field, Type, Writable by user, and Description — but no "Storage location" or "Entity table column" references

### Requirement: Entity availability is described without SQL
Sec3 §3.3 SHALL describe `is_available` as a boolean field governing default query visibility, the `superseded_by` system relationship, and the atomic supersession SDK operation. It SHALL NOT contain SQL examples, partial index definitions, or references to table-level implementation.

#### Scenario: Availability section contains no SQL
- **WHEN** a reader views sec3 §3.3
- **THEN** there are no SQL code blocks, no `CREATE INDEX` statements, and no `WHERE` clause examples

### Requirement: External IDs are described conceptually
Sec3 §3.4 SHALL describe external IDs as a concept (zero or more per entity, keyed by system name, immutable with supersession for corrections) without defining a table schema. The table schema SHALL be in the relational storage section only.

#### Scenario: External IDs section has no table schema
- **WHEN** a reader views sec3 §3.4
- **THEN** there is no table schema definition — only a description of the external ID concept, lookup behavior, immutability rule, and correction mechanism

### Requirement: Relationships are described conceptually
Sec3 §3.9 SHALL describe how relationships work (edge-based, typed, with cardinality constraints enforced by the SDK, immutable with status-based removal) without defining a table schema.

#### Scenario: Relationships section has no table schema
- **WHEN** a reader views sec3 §3.9
- **THEN** there is no table schema definition — only the conceptual model of relationships, their properties, cardinality enforcement, and immutability semantics

### Requirement: Schema versioning rules are separated from migration DDL
Sec3 §3.10 SHALL define the conceptual migration rules (what changes are allowed, rejected, or require manual intervention) without referencing DDL operations (CREATE TABLE, ALTER TABLE, ADD COLUMN). DDL mechanics SHALL be in the relational storage section only. The `hippo_meta` table schema SHALL be removed from sec3.

#### Scenario: Migration rules table uses conceptual language
- **WHEN** a reader views the migration rules table in sec3
- **THEN** actions are described in terms of system behavior (e.g., "Provision new entity type with indexes", "Add field with default or nullable") rather than SQL DDL

### Requirement: DSL examples use domain-neutral types
All schema config examples in sec3 §3.6 SHALL use domain-neutral placeholder types (e.g., `Project`, `Item`, `Attachment`, `Task`) rather than omics-specific types (Subject, Sample, Datafile, etc.). Examples SHALL still demonstrate the full range of DSL features: field types, enums, required/indexed flags, relationships with all cardinality types, inheritance, and relationship properties.

#### Scenario: DSL entity declaration uses neutral types
- **WHEN** a reader views the entity type declaration example in sec3 §3.6
- **THEN** the example uses domain-neutral type names and field names while demonstrating all DSL features

#### Scenario: DSL relationship declaration uses neutral types
- **WHEN** a reader views the relationship declaration example in sec3 §3.6
- **THEN** the relationships use domain-neutral type names and demonstrate one-to-many, many-to-many, many-to-one, and self-referential cardinalities

### Requirement: Schema extensibility example uses domain-neutral types
Sec3 §3.12 SHALL demonstrate schema extension with a domain-neutral example rather than the omics-specific CellLine example.

#### Scenario: Extensibility example is domain-neutral
- **WHEN** a reader views sec3 §3.12
- **THEN** the example shows a new type inheriting from a parent type using domain-neutral names

## REMOVED Requirements

### Requirement: Default omics entity types section (3.7)
**Reason**: The six omics entity types (Subject, Sample, Datafile, Dataset, Workflow, WorkflowRun) are schema configuration, not system design. Their presence in the system spec implies they are privileged or required by the code.
**Migration**: Omics entity types will be defined in a separate schema config document developed at deployment time.

### Requirement: Default schema entity relationship diagram (3.8)
**Reason**: The relationship diagram depicts one schema configuration's shape. Without the entity type definitions it illustrates, it has no place in the system spec.
**Migration**: A relationship diagram will accompany the omics schema config document when developed.
