## Why

After decoupling the default omics schema from the Hippo system spec, the design docs became harder to follow for coding agents. The domain-neutral placeholder types (Project, Item, Task) used in sec3 DSL examples don't carry enough semantic weight to illustrate how a real deployment works. Additionally, several inconsistencies were introduced during restructuring: broken cross-references in sec3b, a contradictory "default schema" comment in sec2, stale INDEX.md decision entries, and leftover domain-specific strings in sec3b that no longer match any described schema.

## What Changes

- Create an **Appendix A** (`appendix_a_example_schema_omics.md`) containing the full omics example schema: all 6 entity types (Subject, Sample, Datafile, Dataset, Workflow, WorkflowRun) with field tables, relationship declarations in Hippo DSL, and the entity relationship graph diagram. Clearly labeled as example deployment configuration.
- Replace the domain-neutral DSL examples in sec3 §3.6 (entity declarations, relationships, inheritance) with excerpts from the omics example schema, each with a labeled callout referencing Appendix A.
- Replace the domain-neutral examples in sec3 §3.9 (validation rules) and §3.10 (extending/replacing) with omics-based examples from Appendix A.
- Update sec3 §3.3 supersede example to use `"Sample"` instead of `"Item"`.
- Fix broken cross-references in sec3b (§3.9→§3.7, §3.10→§3.8 after renumbering).
- Fix sec3b example strings to use omics terms matching the example schema.
- Fix sec2 §2.4 config comment that incorrectly references a "bundled default schema".
- Clean up INDEX.md key decisions: remove stale "Workflow tracking" entry, soften relational language in other entries.

## Capabilities

### New Capabilities
- `example-schema-omics`: Appendix A — a complete, clearly labeled omics example schema used throughout the design spec for illustration. Includes entity type definitions, field tables, relationship declarations, and relationship diagram.

### Modified Capabilities
- `hippo-data-model`: Sec3 DSL examples, validation rules, and schema extension examples updated to use omics excerpts from Appendix A instead of domain-neutral placeholders.

## Impact

- **Design docs**: sec3, sec3b, sec2, and INDEX.md all modified. New appendix file created.
- **No architectural changes**: This is a documentation clarity improvement only.
- **Coding agent impact**: Agents will see concrete, realistic examples that demonstrate how schema config drives the system, while the system spec itself remains generic.
