# Tasks — `hippo-ext-vocabulary`

## 1. Design the `hippo_ext.yaml` schema

- [ ] 1.1 Locate the ship-with-Hippo schema directory (or create `src/hippo/schemas/` if not present) and decide the canonical install path for `hippo_ext.yaml`.
- [ ] 1.2 Author `hippo_ext.yaml` as a LinkML schema declaring the six initial annotations as `Annotation` instances per LinkML's metamodel: `hippo_unique`, `hippo_index`, `hippo_index_partial`, `hippo_search`, `hippo_append_only`, `hippo_accessor`.
- [ ] 1.3 For each annotation, set: `value_type`, `applies_to`, `cardinality` (singleton), `default` (where applicable), and a `description` sourced from sec9 §9.4.
- [ ] 1.4 Declare `hippo_search` with an enumerated `value_type` (initially `fts5`; extensible).
- [ ] 1.5 Add an `id:` URI and a `version:` attribute to `hippo_ext.yaml`; version starts at `0.1.0` (minor-bump discipline per sec9 §9.3).
- [ ] 1.6 Verify the schema loads cleanly with `linkml-validate` against the LinkML metamodel.

## 2. Write the reference doc

- [ ] 2.1 Create `design/reference_hippo_ext.md` following the existing reference-doc template (see `reference_hippo_yaml.md` / `reference_validators_yaml.md`).
- [ ] 2.2 For each annotation: exact value range / enum values, default, `applies_to` targets, interactions with other annotations, and one minimal usage example.
- [ ] 2.3 Document the version field and the add/rename/remove discipline from sec9 §9.4.

## 3. Implement `SchemaRegistry` validation

- [ ] 3.1 Extend `SchemaRegistry` to load `hippo_ext.yaml` at startup (bundled resource) and index the declared annotations by name.
- [ ] 3.2 Implement `_validate_hippo_annotations(schema_view)` that walks every `annotations:` block in the merged view and validates each `hippo_*` key.
- [ ] 3.3 Report undeclared annotations with: offending annotation name, containing class/slot, and the location in `hippo_ext` where declaration should be added.
- [ ] 3.4 Report value-type mismatches with expected vs. actual types and the annotation's declared type.
- [ ] 3.5 Report `applies_to` violations naming both the annotation and the invalid target kind.
- [ ] 3.6 Wire `_validate_hippo_annotations` into the existing schema-load path so failures surface before any subsystem sees the merged view.
- [ ] 3.7 Ensure the validator runs before DDL generation, validator registration, and typed-client generation.

## 4. Tests

- [ ] 4.1 Unit tests for each annotation: declared correctly → passes; undeclared → fails with a message citing `hippo_ext`.
- [ ] 4.2 Unit test: `hippo_index: "yes"` (string value when boolean expected) fails with a type mismatch message.
- [ ] 4.3 Unit test: `hippo_append_only: true` on a slot (wrong `applies_to`) fails naming both the annotation and the target kind.
- [ ] 4.4 Unit test: `hippo_index_partial: true` without `hippo_index: true` surfaces a warning (the behavior is declared as a no-op; test locks in the observed behavior).
- [ ] 4.5 Unit test: `hippo_accessor: "samples"` on a class passes; on a slot fails.
- [ ] 4.6 Integration test: load every `hippo_*`-using schema currently in the repo (test fixtures, example schemas) and verify all pass.

## 5. Docs and schema-spec alignment

- [ ] 5.1 Update `design/INDEX.md` Document Map to reference `reference_hippo_ext.md`.
- [ ] 5.2 Update sec9 §9.4's "Current vocabulary" table if any annotation metadata drifts during implementation (e.g., clearer default semantics for `hippo_accessor`).
- [ ] 5.3 Confirm the `sec9_decisions.md` entry for annotation vocabulary does not need updates (decisions should hold; if they don't, flag for review).

## 6. Migration / rollout

- [ ] 6.1 Audit existing user-schema fixtures and example schemas in `schemas/`, `tests/fixtures/`, and `docs/` for any `hippo_*` usage that doesn't match the initial vocabulary. Fix usages or expand the vocabulary via §1.
- [ ] 6.2 Audit Python code for hardcoded `hippo_*` annotation reading that bypasses `SchemaRegistry` — eliminate in favor of the registry path.
- [ ] 6.3 Run the full test suite against the new load-time validation to catch any previously-silent mistakes.

## 6b. Delete `hippo_default`

No production deployments → straight deletion, no backward-compat migration.

- [ ] 6b.1 Grep user-schema fixtures for `hippo_default:`. For each occurrence: replace with `ifabsent: <value>` if the default is genuinely desired, or delete the line if it isn't. Decide per-occurrence during the edit.
- [ ] 6b.2 Delete `HIPPO_DEFAULT` constant from `src/hippo/linkml_bridge.py`.
- [ ] 6b.3 Update `src/hippo/core/storage/ddl_generator.py` to read `slot.ifabsent` instead of `annotation_value(slot, HIPPO_DEFAULT)`.
- [ ] 6b.4 Same update for `src/hippo/core/storage/pg_ddl_generator.py`.
- [ ] 6b.5 Same update for `src/hippo/core/storage/migration.py` and `src/hippo/core/storage/pg_migration.py`.
- [ ] 6b.6 Same update for `src/hippo/core/storage/schema_diff.py` (replace the `"hippo_default"` string literal with a `slot.ifabsent` read).
- [ ] 6b.7 Delete any tests specific to `hippo_default` behavior; extend existing DDL-default tests to cover `ifabsent` expression forms (literal, `uuid()`, `datetime(now)`, `int(0)`).
- [ ] 6b.8 Confirm after this sub-task: `hippo_ext.yaml` contains no reference to `hippo_default`; no Python file imports or mentions `HIPPO_DEFAULT`; no user-schema fixture uses the annotation.

## 7. Acceptance check

- [ ] 7.1 `SchemaRegistry` fails to load a schema with an undeclared `hippo_*` annotation and the error names the offending element.
- [ ] 7.2 Every `hippo_*` annotation used anywhere in the repo validates against `hippo_ext` with no schema edits beyond declaring the vocabulary itself.
- [ ] 7.3 Full test suite green, including the new validation tests.
- [ ] 7.4 `reference_hippo_ext.md` published and linked from `INDEX.md`.
