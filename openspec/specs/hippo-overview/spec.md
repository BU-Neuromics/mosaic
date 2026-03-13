## MODIFIED Requirements

### Requirement: Glossary contains only system-level terms
The sec1 glossary (§1.8) SHALL define only terms that are part of the Hippo system regardless of schema configuration: Entity, Adapter, Provenance record, Schema config, Field, Relationship, External ID. Domain-specific terms (Donor, Sample, DataFile, BrainRegion, Modality, Dataset) SHALL be removed.

#### Scenario: Glossary has no domain-specific terms
- **WHEN** a reader views the sec1 glossary
- **THEN** every term defined is a system-level concept that applies to any Hippo deployment regardless of schema configuration

#### Scenario: Key system concepts are defined
- **WHEN** a reader views the sec1 glossary
- **THEN** the terms Entity, Adapter, Provenance record, Schema config, Field, Relationship, and External ID are all defined

### Requirement: Scope language is domain-neutral
Sec1 §1.1 and §1.2 SHALL describe Hippo as a generic metadata tracking service that can be configured for any domain. References to omics, biological samples, donors, and data files SHALL be generalized or presented as one example use case rather than the defining purpose.

#### Scenario: Overview describes a generic system
- **WHEN** a reader views sec1 §1.1
- **THEN** Hippo is described as a configurable metadata tracking service, with omics mentioned only as an example deployment context — not as the system's inherent purpose

### Requirement: Non-goals remain applicable
Sec1 §1.4 non-goals that reference domain-specific concepts (e.g., "biological analysis", "donor clinical data", "tissue inventory") SHALL be generalized to their system-level equivalents (e.g., "domain-specific analysis", "upstream source system data").

#### Scenario: Non-goals are domain-neutral
- **WHEN** a reader views sec1 §1.4
- **THEN** non-goals describe what the system does not do in generic terms, without assuming an omics domain
