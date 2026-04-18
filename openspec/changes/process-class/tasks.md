# Tasks — `process-class`

## 1. Declare `Process` in `hippo_core.yaml`

- [ ] 1.1 Add class `Process` to `hippo_core.yaml` with `is_a: Entity`, `class_uri: prov:Activity`, and a short class-level description citing sec9 §9.5.
- [ ] 1.2 Declare slots: `parent_process_id` (range: Process, identifier ref, required: false), `operation_kind` (range: string, required: true), `started_at` (range: datetime, required: true), `ended_at` (range: datetime, required: false), `actor_id` (range: Entity, identifier ref, required: true).
- [ ] 1.3 Annotate `started_at` and `operation_kind` with `hippo_index: true` for common query paths; document in the reference doc.
- [ ] 1.4 Bump `hippo_core` minor version to reflect the additive class.
- [ ] 1.5 Validate updated `hippo_core.yaml` loads with `linkml-validate`.

## 2. DDL generation for `Process`

- [ ] 2.1 Run the existing DDL generator against the updated `hippo_core.yaml` and confirm it emits a `process` table with the expected columns.
- [ ] 2.2 Confirm the annotation-driven indexes on `operation_kind` and `started_at` are emitted.
- [ ] 2.3 Add a migration that creates the `process` table in existing SQLite and PostgreSQL deployments.
- [ ] 2.4 Confirm the self-referential FK on `parent_process_id` is generated correctly (pointing at `process.id`).
- [ ] 2.5 For the Neo4j adapter (if present as a stub): ensure `:Process` label is handled and `parent_process_id` maps to a `:HAS_PARENT` relationship or similar — defer to adapter design; document whatever choice is made.

## 3. SDK integration

- [ ] 3.1 Verify `HippoClient.create("Process", {...})` works through the generic path — creates the `Process` row, registers it in `_entity_registry`, emits a `create` provenance record.
- [ ] 3.2 Verify `HippoClient.get(process_uuid)` resolves to a `Process` without an explicit `entity_type` hint (via the registry).
- [ ] 3.3 Verify `HippoClient.update(process_uuid, {"ended_at": <ts>})` emits an `update` provenance record.
- [ ] 3.4 Confirm availability-change path works: `client.archive(process_uuid)` → `is_available: false`, `availability_change` event, `Status: archived`.

## 4. `is_a: Process` subclass support

- [ ] 4.1 Add a test-fixture subclass `PipelineRun is_a Process` (in `tests/fixtures/`) with a couple of extra slots (`pipeline_name`, `parameters`).
- [ ] 4.2 Verify DDL generation handles the subclass per the existing `is_a` inheritance strategy (single-table or joined, consistent with sec3b).
- [ ] 4.3 Verify `HippoClient.create("PipelineRun", {...})` populates both the Process-inherited columns and the subclass's extra columns.
- [ ] 4.4 Verify querying `Process` returns the parent-class view including the PipelineRun instances (polymorphism per sec3b).

## 5. Parent/child Process tree

- [ ] 5.1 Integration test: create `root_process` with `parent_process_id: null`; create `child_process` with `parent_process_id: root_process.id`.
- [ ] 5.2 Query `SELECT * FROM process WHERE parent_process_id = ?` returns the child.
- [ ] 5.3 Recursive CTE query descending the tree works (`WITH RECURSIVE ...`).
- [ ] 5.4 Neo4j equivalent: `MATCH (p:Process {id: $id})<-[:HAS_PARENT*]-(descendant)` returns descendants. (Adapter-specific; skip if not yet implemented.)

## 6. Reference doc

- [ ] 6.1 Extend `reference_hippo_core.md` with a `Process` section: slot inventory, example YAML declaration, lifecycle note (start/end via `update`), and a pointer to sec9 §9.5.
- [ ] 6.2 Document the annotation-driven indexes on `operation_kind` and `started_at`.
- [ ] 6.3 Cross-reference to `provenance-as-linkml-class` for consumer semantics (which will land in Wave 2).

## 7. Tests

- [ ] 7.1 Unit: `Process` creation → DDL row + registry entry + provenance create event.
- [ ] 7.2 Unit: updating `ended_at` emits provenance update.
- [ ] 7.3 Unit: parent/child Process create + tree traversal works.
- [ ] 7.4 Unit: `is_a: Process` subclass via test fixture — full lifecycle.
- [ ] 7.5 Integration: stress test — create 10k Process rows; confirm query latency on `operation_kind` and `started_at` indexes.

## 8. Documentation

- [ ] 8.1 Update `design/sec5_ingestion.md` (light touch, per sec9 revision plan) to note that reference-loader runs SHOULD emit a `Process` with `operation_kind: reference_data_installed`. This sets up Wave 2 integration.
- [ ] 8.2 Update `design/INDEX.md` Document Map entry for `reference_hippo_core.md` to note `Process` is now documented.

## 9. Acceptance check

- [ ] 9.1 `hippo_core.yaml` declares `Process` correctly; loads under `linkml-validate`.
- [ ] 9.2 `process` table exists in SQLite + PostgreSQL (DDL generator emitted it).
- [ ] 9.3 `HippoClient.create/get/update/archive("Process", ...)` all work through the generic path.
- [ ] 9.4 `is_a: Process` subclasses work; DDL, SDK, and queries all handle them.
- [ ] 9.5 Parent/child Process tree traversal works in both adapter families.
- [ ] 9.6 `reference_hippo_core.md` updated with the `Process` section.
- [ ] 9.7 Full test suite green.
