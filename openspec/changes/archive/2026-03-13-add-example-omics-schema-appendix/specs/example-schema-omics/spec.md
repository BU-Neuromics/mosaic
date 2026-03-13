## ADDED Requirements

### Requirement: Example omics schema appendix exists
An appendix document (`appendix_a_example_schema_omics.md`) SHALL exist in `design/` as a clearly labeled example deployment schema. It SHALL contain entity type definitions, field tables, relationship declarations in Hippo DSL, and an entity relationship diagram for an omics research deployment.

#### Scenario: Appendix is clearly labeled as an example
- **WHEN** a coding agent opens `appendix_a_example_schema_omics.md`
- **THEN** the document header explicitly states this is an example deployment configuration, not part of the system spec, and that other domains would author different schemas

### Requirement: Appendix defines all six omics entity types
The appendix SHALL define six entity types: Subject, Sample, Datafile, Dataset, Workflow, and WorkflowRun. Each entity type SHALL include a description, field table (field name, type, required, indexed, notes), and base class declaration.

#### Scenario: Entity type completeness
- **WHEN** a coding agent reads the appendix
- **THEN** it finds definitions for Subject, Sample, Datafile, Dataset, Workflow, and WorkflowRun with complete field tables

### Requirement: Appendix includes full relationship declarations
The appendix SHALL include all relationship declarations in Hippo DSL format, covering: donated (Subject→Sample), derived_from (Sample→Sample, self-referential), generated (Sample→Datafile), input_to (Datafile→WorkflowRun), output_of (Datafile→WorkflowRun), instance_of (WorkflowRun→Workflow), and contains (Dataset→Datafile).

#### Scenario: All cardinality types demonstrated
- **WHEN** a coding agent reads the appendix relationship declarations
- **THEN** it finds examples of one-to-many, many-to-many, many-to-one, and self-referential relationships with properties

### Requirement: Appendix includes entity relationship diagram
The appendix SHALL include an ASCII entity relationship diagram showing the graph shape of the omics schema.

#### Scenario: Diagram matches declarations
- **WHEN** a coding agent views the relationship diagram
- **THEN** every relationship in the diagram corresponds to a declared relationship in the DSL section, and vice versa
