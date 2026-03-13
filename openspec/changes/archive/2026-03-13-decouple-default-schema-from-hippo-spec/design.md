## Context

The Hippo design spec (sec1–sec3) was written with the default omics schema woven throughout as the primary illustrative example. This was practical during initial drafting — concrete types make abstract systems easier to reason about — but the result is a spec that doesn't cleanly separate system design from domain configuration, or conceptual data model from storage implementation.

The spec will be consumed by coding agents to implement Hippo. Ambiguity about what is "system" vs. "configuration" will produce an implementation that hardcodes omics concepts or couples the SDK to relational storage assumptions.

**Current state of the three sections:**

- **Sec1 (Overview):** Glossary defines domain-specific terms (Donor, Sample, DataFile, BrainRegion, Modality) alongside system terms (Entity, Adapter, Provenance record). Scope and non-goals reference omics concepts.
- **Sec2 (Architecture):** Package structure lists entity-specific REST routers (`donors.py`, `samples.py`, etc.). Code examples use entity-specific SDK methods (`client.query.samples(brain_region="hippocampus")`). These contradict the config-driven, schema-agnostic design principle.
- **Sec3 (Data Model):** Interleaves conceptual model (entity structure, field types, relationships, availability semantics) with relational storage implementation (SQL partial indexes, table schemas for `external_ids` and `entity_relationships`, `hippo_meta` table definition, column-level migration rules). Sections 3.7–3.8 describe the default omics schema as if it were part of the system.

## Goals / Non-Goals

**Goals:**

- Sec3 describes a purely conceptual data model: what entities are, what fields they carry, how relationships work, what validation and versioning rules apply — independent of any storage backend.
- Sec1 and sec2 are free of domain-specific schema terms and examples. A reader encounters no omics concepts until they look at a schema config file outside the Hippo system spec.
- Relational storage implementation details (table schemas, SQL, indexing, migration DDL) are extracted into a clearly labeled reference section that a storage adapter implementer can follow.
- DSL examples in sec3 use minimal, domain-neutral placeholder types that illustrate syntax without implying a specific domain.
- The resulting spec structure makes it unambiguous to a coding agent which parts define the generic system and which parts define one possible storage mapping.

**Non-Goals:**

- Rewriting sec1 or sec2 from scratch — changes are surgical edits to remove domain-specific content and fix inconsistencies.
- Designing a new home for the omics schema — that's a separate concern. We simply remove it from the Hippo system spec.
- Changing the actual system design — the conceptual data model, adapter pattern, SDK-first architecture, and provenance system are all sound. This is a documentation restructuring, not a redesign.
- Defining the graph database storage mapping — only the relational mapping is extracted, since that's what currently exists in sec3.

## Decisions

### 1. Where does the relational storage mapping go?

**Decision:** Create a new design doc section (`sec3b_relational_storage.md`) as a sibling to sec3, explicitly scoped as the reference implementation for SQLite/PostgreSQL adapters.

**Alternatives considered:**
- *Appendix within sec3:* Keeps related content together but blurs the conceptual/implementation boundary we're trying to establish.
- *Subsection of sec2 (Architecture):* Sec2 defines the adapter pattern and interfaces; the storage mapping is an implementation of those interfaces, not the interfaces themselves. Mixing them repeats the layering problem.
- *Standalone section (sec8 or similar):* Viable, but the content is tightly coupled to sec3's conceptual model. A sibling file with a clear cross-reference is more navigable.

**Rationale:** A sibling file (`sec3b`) signals "this is the storage-layer companion to sec3" while maintaining physical separation. The `b` suffix makes the relationship obvious. The file's header will state its scope: "This section describes how the conceptual data model defined in sec3 maps to relational storage. It is the reference specification for the SQLite and PostgreSQL storage adapters. Other adapter types (graph, document, etc.) would have their own mapping documents."

### 2. How to handle DSL examples after removing omics types?

**Decision:** Replace omics-specific types in sec3 §3.6 examples with domain-neutral placeholders (`Project`, `Item`, `Attachment`) that demonstrate the same DSL features (field types, enums, relationships, inheritance, cardinality) without implying any domain.

**Alternatives considered:**
- *Use fully abstract names (EntityA, EntityB):* Demonstrates syntax but is harder to read — readers can't form a mental model of what the relationships mean.
- *Keep omics types but add a disclaimer:* We tried this (the callout block in 3.7). It didn't prevent the ambiguity from propagating into sec1 and sec2.

**Rationale:** Domain-neutral but meaningful names let examples be self-explanatory while making it clear no specific domain is privileged. The examples exist to show DSL syntax, not to define a schema.

### 3. How to handle sec2 entity-specific routers and examples?

**Decision:** Replace entity-specific routers (`donors.py`, `samples.py`, etc.) in the package structure with a generic routing pattern (`routers/entities.py`) and update code examples to use the generic query API (`client.query("Sample", ...)` instead of `client.query.samples(...)`).

**Alternatives considered:**
- *Keep entity-specific routers as "generated from schema":* Adds complexity (code generation from config) and is an implementation decision that doesn't belong in the architecture spec.
- *Remove router examples entirely:* Too sparse — sec2 needs to show how the REST layer works.

**Rationale:** Generic routing is the natural consequence of config-driven schema. The REST layer should dispatch based on entity type strings resolved from the schema config, not hardcoded per-type router modules. This aligns sec2 with the design principles stated in sec1.

### 4. What to do with sec3 §3.12 (Extending or Replacing the Schema)?

**Decision:** Keep the section but replace the omics-specific CellLine example with a domain-neutral example that demonstrates the same features (inheritance, new fields, new relationships).

**Rationale:** This section explains an important system capability (schema extensibility). It just needs a domain-neutral illustration.

## Risks / Trade-offs

**[Loss of concrete illustration]** → Readers lose the ability to mentally "run" the system against real types while reading the spec. **Mitigation:** The domain-neutral DSL examples in sec3 still demonstrate all features. The omics schema can be referenced as a separate worked example when it's developed. Add a brief note in sec3 pointing to where deployment-specific schemas will live.

**[Increased abstraction in sec2]** → Generic routing is harder to visualize than named routers. **Mitigation:** The sec2 code examples will show concrete request/response flows using placeholder entity types, making the pattern clear without hardcoding domain types.

**[Scope creep into sec2 redesign]** → Fixing the router structure could cascade into rethinking the package layout, dependency injection, and REST layer design. **Mitigation:** Changes to sec2 are limited to: (a) replacing entity-specific router filenames with generic ones, (b) updating code examples to use generic query API, (c) cleaning domain terms from the glossary. No architectural changes.

**[Orphaned omics schema]** → The default schema content has no home after removal. **Mitigation:** This is acceptable. The omics schema is configuration that will be authored when we implement a specific deployment. It doesn't need to exist yet.

## Migration Plan

This is a documentation-only change. There is no deployment, rollback, or data migration concern. The restructuring is applied as edits to the existing markdown files in `hippo/design/`.

**Execution order:**

1. Create `sec3b_relational_storage.md` — extract all relational implementation content from sec3 into the new file.
2. Edit sec3 — remove storage implementation details, remove default schema sections (3.7, 3.8), rewrite system fields table, replace DSL examples with domain-neutral types, update 3.12 example.
3. Edit sec1 — clean glossary, generalize scope language.
4. Edit sec2 — replace entity-specific routers and code examples with generic equivalents.
5. Update `INDEX.md` — add new section entry, update sec3 status and key decisions.

Order matters: sec3b must be created first so that content is moved (not lost) before sec3 is trimmed. Sec3 edits come before sec1/sec2 since the data model is the foundation the other sections reference.

## Open Questions

- **Naming of the relational storage section:** Is `sec3b_relational_storage.md` the right convention, or should it get its own number (e.g., `sec8_relational_storage.md`)? The `3b` suffix communicates the tight coupling to sec3 but breaks the sequential numbering pattern.
- **Where does the omics schema ultimately live?** Options: `schemas/omics/` in this repo, a separate config repo, or deferred entirely. Not blocking for this change, but worth deciding before implementation begins.
