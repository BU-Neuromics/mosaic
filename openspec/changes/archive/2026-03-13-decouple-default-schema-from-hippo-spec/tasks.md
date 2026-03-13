## 1. Create relational storage mapping section

- [x] 1.1 Create `hippo/design/sec3b_relational_storage.md` with header, scope statement, and dependency/feeds-into declarations
- [x] 1.2 Move entity table schema definition into sec3b (physical columns: `id`, `is_available`, user-defined fields from schema config)
- [x] 1.3 Move partial index SQL pattern (`CREATE INDEX ... WHERE is_available = true`) from sec3 §3.3 into sec3b
- [x] 1.4 Move `external_ids` table schema from sec3 §3.4 into sec3b
- [x] 1.5 Move `entity_relationships` table schema from sec3 §3.9 into sec3b
- [x] 1.6 Move `hippo_meta` table schema and standard keys from sec3 §3.10 into sec3b
- [x] 1.7 Move migration DDL mechanics (CREATE TABLE, ALTER TABLE ADD COLUMN, etc.) from sec3 §3.10 into sec3b, keeping conceptual rules in sec3
- [x] 1.8 Add computed field derivation guidance (how `created_at`, `updated_at`, `schema_version` are derived from provenance log in SQL context)

## 2. Rewrite sec3 as conceptual data model

- [x] 2.1 Rewrite §3.1 to remove references to "entity table" and relational storage; describe the conceptual entity structure only
- [x] 2.2 Rewrite §3.2 system fields table: remove "Storage location" column, add "Description" column, describe all fields as caller-visible concepts
- [x] 2.3 Rewrite §3.3: remove SQL code block and partial index details; describe availability semantics, default query behavior, and supersession in conceptual terms only
- [x] 2.4 Rewrite §3.4: remove table schema; describe external IDs as a concept (cardinality, lookup, immutability, correction/supersession mechanism)
- [x] 2.5 Rewrite §3.6 DSL examples: replace omics types (Subject, Sample, Datafile, etc.) with domain-neutral types (Project, Item, Attachment, Task); ensure all DSL features are still demonstrated (field types, enums, required/indexed, all cardinality types, inheritance, relationship properties)
- [x] 2.6 Remove §3.7 (Default Schema: Omics Entity Types) entirely
- [x] 2.7 Remove §3.8 (Default Schema: Entity Relationship Graph) entirely
- [x] 2.8 Rewrite §3.9: remove table schema; describe relationship model conceptually (edge-based, typed, cardinality enforcement by SDK, immutable with status removal)
- [x] 2.9 Rewrite §3.10 migration rules table: replace DDL language with conceptual language; remove `hippo_meta` table schema (now in sec3b); keep deprecated field communication section
- [x] 2.10 Rewrite §3.12: replace CellLine example with domain-neutral inheritance example
- [x] 2.11 Renumber sections if needed after removing 3.7 and 3.8 (or leave gaps with a note)

## 3. Clean sec1 (Overview)

- [x] 3.1 Rewrite §1.1 to describe Hippo as a generic configurable metadata tracking service; mention omics only as an example deployment context
- [x] 3.2 Generalize §1.2 deployment philosophy if it contains domain-specific references
- [x] 3.3 Generalize §1.3 platform diagram: replace domain-specific module names (Tissue Registry, Digital Histology Store) with generic labels or mark them as examples
- [x] 3.4 Generalize §1.4 non-goals: replace domain-specific items with system-level equivalents
- [x] 3.5 Rewrite §1.8 glossary: remove Donor, Sample, DataFile, BrainRegion, Modality, Dataset; keep and refine Entity, Adapter, Provenance record; add Schema config, Field, Relationship, External ID

## 4. Clean sec2 (Architecture)

- [x] 4.1 Update §2.2 package structure: replace `routers/donors.py`, `samples.py`, `datafiles.py`, `datasets.py` with `routers/entities.py` (and optionally `relationships.py`, `ingestion.py`)
- [x] 4.2 Update §2.5 code examples: replace `client.query.samples(brain_region="hippocampus")` with `client.query("Sample", brain_region="hippocampus")` pattern
- [x] 4.3 Update §2.5 REST router example to show generic `/{entity_type}` dispatch
- [x] 4.4 Review §2.6 for any domain-specific references and generalize

## 5. Update INDEX.md

- [x] 5.1 Add `sec3b_relational_storage.md` entry to the document map
- [x] 5.2 Update sec3 status and notes to reflect restructuring
- [x] 5.3 Update key decisions log: add decision for separating conceptual model from storage mapping
- [x] 5.4 Remove or update any open questions resolved by this change
