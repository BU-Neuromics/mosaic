## Context

The `decouple-default-schema-from-hippo-spec` change successfully separated system design from domain configuration across sec1–sec3. However, it introduced two problems:

1. **Loss of concrete illustration**: The domain-neutral placeholder types (Project, Item, Task, Attachment) used in sec3 DSL examples don't convey how a real deployment works. For coding agents consuming these docs, realistic examples are more valuable than abstract ones.
2. **Inconsistencies from restructuring**: Broken cross-references in sec3b, a contradictory config comment in sec2, stale INDEX.md entries, and example strings in sec3b that reference omics terms without any schema to anchor them.

The current state of the spec sections:
- **sec3 §3.6** has 4 domain-neutral entity types and 6 relationships as DSL examples
- **sec3 §3.9** has domain-neutral validation examples
- **sec3 §3.10** has a domain-neutral schema extension example (ArchivalItem)
- **sec3b** has stale cross-references (§3.9, §3.10 instead of §3.7, §3.8) and orphaned omics terms in example strings
- **sec2 §2.4** incorrectly says the schema path "Defaults to bundled default_schema.yaml if omitted"
- **INDEX.md** has stale key decisions referencing the removed default schema and relational-specific language

## Goals / Non-Goals

**Goals:**

- A complete omics example schema in a clearly labeled appendix, usable as the single source of illustrative examples throughout the spec.
- All DSL examples in sec3 use excerpts from the omics example schema, with callouts identifying them as examples from Appendix A.
- All cross-references between sec3 and sec3b are correct after the renumbering from the previous change.
- All inconsistencies introduced by the decoupling change are resolved.

**Non-Goals:**

- Changing any system design decisions — this is purely a documentation quality improvement.
- Making the omics schema a "default" or "bundled" schema — it is explicitly labeled as an example.
- Modifying sec1 — the overview should remain generic and domain-neutral.
- Modifying sec2 beyond fixing the config comment — the architecture is schema-independent.

## Decisions

### 1. Appendix file naming and location

**Decision:** `design/appendix_a_example_schema_omics.md` — sibling to the numbered sections.

**Rationale:** The `appendix_` prefix signals supplementary material. The `a_` allows for future appendices (e.g., `appendix_b_example_schema_manufacturing.md`). Lives in `design/` alongside the sections that reference it.

### 2. Callout format for inline examples

**Decision:** Each omics excerpt in sec3 is preceded by a blockquote callout:

```markdown
> **Example (omics deployment):** The following is excerpted from the example
> omics schema in Appendix A. See appendix_a_example_schema_omics.md for the
> complete schema.
```

**Rationale:** Blockquotes are visually distinct. The text makes it unambiguous to a coding agent that this is illustrative, not system-level. The file reference lets agents find the full schema.

### 3. Replace domain-neutral examples entirely (not supplement)

**Decision:** The omics examples replace the Project/Item/Task examples rather than coexisting alongside them.

**Rationale:** Two different example schemas in the same section creates confusion about which is canonical. The omics schema is rich enough to demonstrate all DSL features (field types, enums, required/indexed, all cardinality types, inheritance, relationship properties). One clear example is better than two competing ones.

## Risks / Trade-offs

**[Omics bias perception]** → A reader might assume Hippo is an omics tool despite the generic system spec. **Mitigation:** The appendix header and every inline callout explicitly state this is one example deployment configuration. The system spec text (§3.1, §3.6 prose, §3.10 prose) remains generic.

**[Example coupling]** → Changes to the omics schema in the appendix require updating excerpts in sec3. **Mitigation:** Acceptable because the appendix is the source of truth and excerpts are small. The appendix is unlikely to change frequently since it's illustrative, not normative.
