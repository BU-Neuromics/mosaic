## MODIFIED Requirements

### Requirement: DSL examples use omics schema excerpts
All schema config examples in sec3 §3.6 SHALL use entity types and relationships from the omics example schema in Appendix A. Each example SHALL be preceded by a blockquote callout identifying it as an excerpt from Appendix A. Examples SHALL demonstrate the full range of DSL features: field types, enums, required/indexed flags, relationships with all cardinality types, inheritance, and relationship properties.

#### Scenario: Entity type declaration example uses omics types
- **WHEN** a coding agent reads the entity type declaration example in sec3 §3.6
- **THEN** the example shows a Subject or Sample entity type from the omics schema with a callout referencing Appendix A

#### Scenario: Relationship declaration example uses omics types
- **WHEN** a coding agent reads the relationship declaration example in sec3 §3.6
- **THEN** the relationships use omics entity types (Subject, Sample, Datafile, etc.) and demonstrate one-to-many, many-to-many, many-to-one, and self-referential cardinalities

#### Scenario: Inheritance example uses omics types
- **WHEN** a coding agent reads the schema inheritance example in sec3 §3.6
- **THEN** the example shows BrainSample extending Sample with domain-relevant fields

### Requirement: Validation rules example uses omics types
The validation rules example in sec3 §3.9 SHALL use field names from the omics example schema (e.g., modality, uri, read_count, external_id).

#### Scenario: Validation example matches omics schema
- **WHEN** a coding agent reads the validation rules example in sec3 §3.9
- **THEN** the field names correspond to fields defined in the omics example schema in Appendix A

### Requirement: Schema extension example uses omics types
The schema extension example in sec3 §3.10 SHALL use a CellLine entity type extending Sample, consistent with the omics domain.

#### Scenario: Extension example uses CellLine
- **WHEN** a coding agent reads the schema extension example in sec3 §3.10
- **THEN** it shows a CellLine type with `base: Sample` and domain-relevant fields

### Requirement: Cross-references between sec3 and sec3b are correct
All section cross-references in sec3b SHALL use the correct section numbers from the renumbered sec3 (Relationship Model = §3.7, Schema Versioning = §3.8).

#### Scenario: sec3b relationship cross-reference
- **WHEN** a coding agent reads sec3b §3b.4
- **THEN** the cross-reference points to sec3 §3.7 (not §3.9)

#### Scenario: sec3b migration cross-reference
- **WHEN** a coding agent reads sec3b §3b.6
- **THEN** cross-references to the conceptual migration rules point to sec3 §3.8 (not §3.10)

### Requirement: No contradictory default schema references
Sec2 §2.4 config system SHALL NOT reference a "bundled default schema" or imply that a schema is automatically provided if the config path is omitted.

#### Scenario: Config comment is accurate
- **WHEN** a coding agent reads the schema path comment in sec2 §2.4
- **THEN** there is no mention of a "default" or "bundled" schema — the comment indicates a schema path is required

### Requirement: INDEX.md key decisions are current
The INDEX.md key decisions log SHALL NOT contain entries that reference the removed default omics schema as a system-level decision. Entries using relational-specific language (e.g., "entity tables", "partial indexes") for conceptual decisions SHALL use storage-neutral language.

#### Scenario: No stale default schema decision
- **WHEN** a coding agent reads the INDEX.md key decisions
- **THEN** there is no entry referencing "WorkflowRun in default schema" as a system decision

#### Scenario: Conceptual decisions use neutral language
- **WHEN** a coding agent reads the INDEX.md key decisions for temporal metadata and entity lifecycle
- **THEN** the language describes conceptual behavior without relational storage terms

### Requirement: Entity type strings support optional namespace qualification
The data model SHALL document that entity type strings are optionally namespace-qualified. A bare entity type string (e.g., `"Sample"`) SHALL refer to the root namespace. A qualified string (e.g., `"tissue.Sample"`) SHALL refer to the named namespace. Both forms SHALL be valid wherever entity type is accepted: SDK calls, REST query parameters, schema field references, and provenance records.

#### Scenario: Namespaced entity type stored and retrieved by FQN
- **WHEN** an entity is ingested with `entity_type = "tissue.Sample"`
- **THEN** the entity type is stored verbatim as `"tissue.Sample"` and returned as-is in query results and provenance records

#### Scenario: Root-namespace entity type stored and retrieved as bare string
- **WHEN** an entity is ingested with `entity_type = "Donor"` (no namespace prefix)
- **THEN** the entity type is stored verbatim as `"Donor"` and `root.Donor` is treated as an equivalent alias at the SDK level only (not in storage)

#### Scenario: `tissue.Sample` and `omics.Sample` are distinct entity types
- **WHEN** entities with `entity_type = "tissue.Sample"` and `entity_type = "omics.Sample"` are both present in storage
- **THEN** querying for `"tissue.Sample"` returns only tissue samples and querying for `"omics.Sample"` returns only omics samples
