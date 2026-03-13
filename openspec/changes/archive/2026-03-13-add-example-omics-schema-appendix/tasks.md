## 1. Create Appendix A (omics example schema)

- [x] 1.1 Create `design/appendix_a_example_schema_omics.md` with header, scope statement, and disclaimer that this is example configuration
- [x] 1.2 Add Subject entity type definition with field table
- [x] 1.3 Add Sample entity type definition with field table
- [x] 1.4 Add Datafile entity type definition with field table
- [x] 1.5 Add Dataset entity type definition with field table
- [x] 1.6 Add Workflow entity type definition with field table
- [x] 1.7 Add WorkflowRun entity type definition with field table
- [x] 1.8 Add full relationship declarations in Hippo DSL format (all 7 relationships)
- [x] 1.9 Add entity relationship graph ASCII diagram

## 2. Update sec3 DSL examples to use omics excerpts

- [x] 2.1 Replace §3.6 entity type declaration example (Project/Item/Attachment/Task → Subject + Sample excerpt from Appendix A) with callout
- [x] 2.2 Replace §3.6 relationship declaration example with omics relationships from Appendix A, with callout
- [x] 2.3 Replace §3.6 schema inheritance example (PriorityItem → BrainSample) with callout
- [x] 2.4 Update §3.3 supersede example: change `"Item"` to `"Sample"` and use omics-appropriate reason
- [x] 2.5 Update §3.5 `ref` type example from `"item:abc-123"` to `"sample:abc-123"`

## 3. Update sec3 validation and extension examples

- [x] 3.1 Replace §3.9 validation rules example with omics field names (modality, uri, read_count, external_id)
- [x] 3.2 Replace §3.10 schema extension example (ArchivalItem → CellLine extending Sample)

## 4. Fix sec3b cross-references and example strings

- [x] 4.1 Fix §3b.4 cross-reference: "sec3 §3.9" → "sec3 §3.7"
- [x] 4.2 Fix §3b.6 cross-references: "sec3 §3.10" → "sec3 §3.8" (two occurrences)
- [x] 4.3 Update §3b.3 external_ids system examples to use omics terms with Appendix A reference
- [x] 4.4 Update §3b.4 relationship examples from "donated" to terms matching Appendix A

## 5. Fix sec2 and INDEX.md inconsistencies

- [x] 5.1 Fix sec2 §2.4 config comment: remove "Defaults to bundled default_schema.yaml if omitted"
- [x] 5.2 Remove INDEX.md "Workflow tracking" key decision (no longer a system-level decision)
- [x] 5.3 Update INDEX.md "Temporal metadata" entry: replace "entity tables" with storage-neutral language
- [x] 5.4 Update INDEX.md "Entity lifecycle" entry: move "partial indexes" detail out, keep conceptual language
