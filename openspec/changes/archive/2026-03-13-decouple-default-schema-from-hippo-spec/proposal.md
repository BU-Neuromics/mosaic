## Why

The Hippo design spec (sec1–sec3) mixes domain-specific omics schema content with the generic, schema-agnostic system design. Default schema entity types (Subject, Sample, Datafile, etc.) appear in the glossary, package structure, code examples, and data model sections as if they are system-level concepts. Section 3 also interleaves conceptual data model definitions with relational storage implementation details (SQL indexes, table schemas, column types). This creates two problems: (1) a coding agent implementing Hippo could hardcode domain-specific types or couple the core SDK to relational storage, and (2) the spec cannot cleanly serve non-omics deployments or non-relational storage adapters.

## What Changes

- **BREAKING**: Remove the default omics schema (sec3 §3.7, §3.8) from the Hippo system spec entirely. The omics entity types, field tables, and relationship diagram are configuration — not system design — and will be developed separately when implementing a specific deployment.
- **BREAKING**: Remove omics-specific terms (Donor, Sample, DataFile, BrainRegion, Modality) from the sec1 glossary. Replace with system-level terms only.
- **BREAKING**: Replace entity-specific REST routers (`donors.py`, `samples.py`, etc.) and entity-specific SDK query examples in sec2 with generic, config-driven equivalents consistent with the adapter pattern.
- Separate sec3 into two concerns: (a) the conceptual data model (entity structure, fields, types, relationships, availability, validation, versioning rules) and (b) the relational storage reference implementation (table schemas, indexes, migration mechanics, `hippo_meta`). The storage implementation detail moves out of sec3.
- Remove SQL examples and table schemas from sec3, including `external_ids` table schema (§3.4), `entity_relationships` table schema (§3.9), partial index SQL (§3.3), and `hippo_meta` table (§3.10).
- Remove "Storage location" column from the sec3 system fields table (§3.2). Reframe system fields as conceptual fields visible to callers, not physical storage decisions.
- Update sec3 §3.6 DSL examples to use domain-neutral placeholder types instead of omics-specific types.
- Retain sec3 §3.12 (Extending or Replacing the Schema) but remove the omics-specific CellLine example; replace with a domain-neutral illustration.

## Capabilities

### New Capabilities
- `relational-storage-mapping`: Reference specification for how the conceptual data model maps to relational storage (SQLite/PostgreSQL). Covers table schemas, indexing strategy, `hippo_meta`, migration DDL mechanics. Extracted from current sec3.

### Modified Capabilities
- `hippo-data-model`: Sec3 rewritten as a purely conceptual data model — what entities look like to callers, independent of storage backend. All relational implementation detail removed.
- `hippo-overview`: Sec1 glossary and scope language cleaned of domain-specific schema terms.
- `hippo-architecture`: Sec2 package structure, code examples, and router design updated to reflect generic entity routing consistent with config-driven schema.

## Impact

- **Design docs**: sec1, sec2, sec3 all modified. A new section or appendix created for relational storage mapping.
- **Downstream sections**: sec4 (API layer, not yet started) benefits — will be written against the generic conceptual model from the start rather than needing a later decoupling pass.
- **Default omics schema**: Removed from Hippo spec. Will need its own home (separate config repo, deployment-specific docs, or a `schemas/omics/` directory outside the Hippo component) when implementation begins.
- **No code impact**: This is a documentation-only repository. Changes affect spec structure, not running software.
