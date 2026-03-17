## 1. Data Model Spec Updates (sec3)

- [x] 1.1 Update DSL examples in sec3 §3.6 to use omics entity types (Subject, Sample, Datafile) with Appendix A callout blockquotes
- [x] 1.2 Add examples covering all DSL feature range: field types, enums, required/indexed flags, relationships with all cardinality types, inheritance, and relationship properties
- [x] 1.3 Update relationship declaration example in sec3 §3.6 to demonstrate one-to-many, many-to-many, many-to-one, and self-referential cardinalities using omics types
- [x] 1.4 Update inheritance example in sec3 §3.6 to show BrainSample extending Sample
- [x] 1.5 Update validation rules example in sec3 §3.9 to use omics field names (modality, uri, read_count, external_id)
- [x] 1.6 Update schema extension example in sec3 §3.10 to show CellLine extending Sample with `base: Sample` and domain-relevant fields
- [x] 1.7 Add section to sec3 documenting namespace-qualified entity type string semantics: bare strings resolve to root namespace, `tissue.Sample` resolves to named namespace, both forms valid in SDK, REST, schema references, and provenance records

## 2. Architecture & Config Spec Updates (sec2 and INDEX.md)

- [x] 2.1 Remove reference to "bundled default schema" from sec2 §2.4 config system — replace comment to indicate schema path is required
- [x] 2.2 Remove stale INDEX.md key decision referencing "WorkflowRun in default schema" as a system-level decision
- [x] 2.3 Update INDEX.md key decisions for temporal metadata and entity lifecycle to use storage-neutral language (replace "entity tables", "partial indexes" with conceptual terms)

## 3. Cross-Reference Corrections (sec3b)

- [x] 3.1 Update sec3b §3b.4 cross-reference to point to sec3 §3.7 (Relationship Model, not §3.9)
- [x] 3.2 Update sec3b §3b.6 cross-references for migration rules to point to sec3 §3.8 (Schema Versioning, not §3.10)

## 4. Schema Namespaces Spec (new section or appendix)

- [x] 4.1 Document `namespace:` key syntax and semantics: optional top-level key, entities scoped to named namespace, files without key contribute to root namespace
- [x] 4.2 Document multi-file namespace merging behavior: same `namespace` value across files merges entity lists; duplicate `(namespace, entity_name)` raises `SchemaValidationError`
- [x] 4.3 Document FQN semantics: `<namespace>.<EntityType>` for named namespaces; bare `<EntityType>` and `root.<EntityType>` are equivalent for root namespace; `root` is the only implicit prefix
- [x] 4.4 Document `NamespaceRegistry` construction: built by `SchemaLoader` at load time, fully populated before cross-namespace reference validation, maps `(namespace, entity_name)` to `EntityConfig`
- [x] 4.5 Document cross-namespace reference resolution: `references.entity_type` supports FQNs; resolved at validation time; unknown FQN raises `SchemaValidationError` identifying the unresolved reference and file
- [x] 4.6 Document circular dependency detection: namespace dependency graph derived from cross-namespace references; cycles raise `SchemaValidationError` with cycle path identified
- [x] 4.7 Document backwards compatibility guarantee: schemas with no `namespace` key load unchanged; no YAML structure changes required; existing `HippoClient` calls unaffected
- [x] 4.8 Document root-namespace canonicalization invariant: `root.Donor` is normalized to `"Donor"` at registry ingestion; only unqualified form appears in `SchemaConfig` and storage

## 5. Schema Compilation and Validation Spec Updates

- [x] 5.1 Update `hippo validate --schema` docs to specify that namespace graph validation (cross-namespace reference checks, duplicate entity detection, circular dependency detection) is included in the validation pass
- [x] 5.2 Document error messages for namespace validation failures: each error identifies the unresolved FQN or circular dependency path and the file where it originates
- [x] 5.3 Update `hippo migrate` docs to note that namespace graph validation runs at migration time alongside existing schema validation

## 6. Design Spec Alignment Checks

- [x] 6.1 Verify all spec cross-references added in tasks 4.x and 5.x are consistent with decisions D1–D5 in design.md
- [x] 6.2 Verify OQ1 (entity type remapping) and OQ2 (root canonical form) are surfaced as open questions in INDEX.md or relevant spec sections
- [x] 6.3 Review updated specs end-to-end to confirm no contradictions between hippo-data-model, schema-namespaces, and schema-compilation-and-validation specs
