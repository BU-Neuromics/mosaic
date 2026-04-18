# Tasks — `hippo-core-schema`

## 1. Author `hippo_core.yaml`

- [ ] 1.1 Create `src/hippo/schemas/hippo_core.yaml` alongside `hippo_ext.yaml`.
- [ ] 1.2 Declare the schema `id:`, `name:`, `version:` (`0.1.0`), and an `imports:` block referencing `hippo_ext` and the LinkML types schema.
- [ ] 1.3 Declare abstract class `Entity` with `class_uri: prov:Entity`, `abstract: true`, and slots `id` (range: string with identifier: true; pattern matching a UUID; required: true) and `is_available` (range: boolean; required: true; ifabsent: `true`).
- [ ] 1.4 Declare enum `Status` with permissible values: `active`, `archived`, `superseded`, `deleted`, `distributed`, `removed` (one-line descriptions each).
- [ ] 1.5 Declare enum `Operation` with permissible values: `create`, `update`, `availability_change`, `supersede`, `relationship_add`, `relationship_remove`, `external_id_add`, `external_id_remove`, `migration_applied`, `reference_data_installed` (one-line descriptions each).
- [ ] 1.6 Declare placeholder classes `Validator` and `ReferenceLoader` with minimal required slots (`name`) and a `TODO:` note pointing at the follow-on changes that finalize their shape.
- [ ] 1.7 Verify `hippo_core.yaml` loads cleanly via `linkml-validate` against the LinkML metamodel.

## 2. Three-layer merge in `SchemaRegistry`

- [ ] 2.1 Add bundled-resource loading for `hippo_core.yaml` (similar to `hippo_ext.yaml` in the previous change).
- [ ] 2.2 Update `SchemaRegistry`'s schema-load method to call `SchemaView.load_schema()` in order: `hippo_ext` → `hippo_core` → user schemas. The resulting merged view is the sole schema representation.
- [ ] 2.3 Validate that every loaded user schema declares `imports: hippo_core` (or transitive import). Fail loudly if missing.
- [ ] 2.4 Read the `hippo_ext` and `hippo_core` version declarations at load time. Enforce major-version compatibility between `hippo_core`'s declared `hippo_ext` target and the installed `hippo_ext`, and between the user schema's declared `hippo_core` target and the installed `hippo_core`. Mismatch → load failure with both versions named.
- [ ] 2.5 Expose the LinkML versions (`hippo_ext`, `hippo_core`) through a `SchemaRegistry.versions` property for introspection and REST `/health` surfacing.

## 3. Migrate existing user schemas to `is_a: Entity`

- [ ] 3.1 Identify every user-schema YAML file in the repo: `schemas/`, `tests/fixtures/`, `docs/`, any example schemas referenced by `design/appendix_a_example_schema_omics.md`.
- [ ] 3.2 For each file, add `imports:` including `hippo_core`.
- [ ] 3.3 For each domain class declared in those files, add `is_a: Entity`. Remove redundant local `id` / `is_available` slot declarations where safe (prefer inheritance).
- [ ] 3.4 Run the full schema-load test suite to confirm every migrated file loads against the merged `SchemaView`.
- [ ] 3.5 Update `design/appendix_a_example_schema_omics.md` to reflect the new import/inheritance pattern.

## 4. Reference documentation

- [ ] 4.1 Create `design/reference_hippo_core.md` following the existing reference-doc template.
- [ ] 4.2 Document `Entity` (slots, PROV-O class URI, abstract-only contract).
- [ ] 4.3 Document `Status` and `Operation` enum values with one-line semantics each.
- [ ] 4.4 Document `Validator` and `ReferenceLoader` as placeholder classes with pointers to the follow-on OpenSpec changes that finalize them.
- [ ] 4.5 Document version fields and the compatibility discipline per sec9 §9.3.
- [ ] 4.6 Update `design/INDEX.md` Document Map to include `reference_hippo_core.md`.

## 5. Tests

- [ ] 5.1 Unit test: `SchemaRegistry` loads `hippo_core` successfully and reports its version.
- [ ] 5.2 Unit test: user schema without `imports: hippo_core` fails at load with a clear message.
- [ ] 5.3 Unit test: user schema with `is_a: Entity` on every class passes.
- [ ] 5.4 Unit test: user schema redeclaring `id` on a domain class succeeds (explicit redeclaration is legal).
- [ ] 5.5 Unit test: user schema declaring a domain slot named `is_available` with a different type fails (can't override inherited slot incompatibly).
- [ ] 5.6 Unit test: version-mismatch scenarios for both (`hippo_core` → `hippo_ext`) and (user schema → `hippo_core`) fail with clear messages.
- [ ] 5.7 Integration test: every schema file in the repo loads successfully against the merged view without manual fixes.

## 6. Documentation updates

- [ ] 6.1 Update `design/sec1_overview.md` and `design/sec2_architecture.md` where they mention the schema-loading pipeline to reflect `hippo_ext` + `hippo_core` imports (light touch, per sec9 revision plan).
- [ ] 6.2 Update `design/INDEX.md` Key Decisions Log — confirm the "Schema authoring: Direct LinkML" decision now cites the three-layer stack (already done in the sec9 approval commit; verify).

## 7. Acceptance check

- [ ] 7.1 `SchemaRegistry` merges `hippo_ext` + `hippo_core` + user schemas into one `SchemaView`; startup reports both shipped-schema versions.
- [ ] 7.2 Every repo schema uses `imports: hippo_core` and `is_a: Entity` correctly.
- [ ] 7.3 Load-time errors for missing imports and version mismatches are clear and actionable.
- [ ] 7.4 `reference_hippo_core.md` published and linked.
- [ ] 7.5 Full test suite green.
- [ ] 7.6 No observable SDK behavior change (spot-check: existing CRUD tests pass unchanged).
