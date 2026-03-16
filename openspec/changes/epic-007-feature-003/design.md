## Context

Hippo already has:
- `DDLGenerator` in `src/hippo/core/storage/ddl_generator.py` - generates CREATE TABLE statements from schema configs
- `MigrationPlanner` and `MigrationExecutor` in `src/hippo/core/storage/migration.py` - plans and executes migrations
- Stub `migrate` CLI command in `src/hippo/cli/main.py` - currently only handles manual SQL files

**What's missing**: The CLI `migrate` command doesn't integrate with the schema system. It doesn't:
1. Load schema definitions from `schemas/` directory
2. Compare against the current database schema
3. Generate migration plans for detected changes
4. Provide a preview mode

## Goals / Non-Goals

**Goals:**
- Implement schema diff engine that detects additive changes from YAML schema files
- Generate migration plans from schema definitions
- Support `--preview` mode to show planned migrations without applying
- Handle non-nullable columns with existing data (add default or warn)
- Report "no migrations needed" for empty schemas or no changes
- Validate schema consistency and report errors for conflicting definitions
- Integrate with existing `MigrationPlanner`/`MigrationExecutor`

**Non-Goals:**
- Schema rollback/revert functionality (future v0.3+)
- Data migration between entity types (future)
- Automatic schema version tracking in database (future v0.2)
- Non-additive schema changes (renames, deletions - out of scope for v0.1)

## Decisions

### D1: Schema Loading Strategy
**Decision:** Load schemas from `schemas/*.yaml` and `schemas/*.yml` files in the current working directory.
**Rationale:** Follows existing convention from `hippo validate` command. Simple and explicit.
**Alternatives considered:**
- Load from `schema.yaml` in project root - too limiting for multiple entity types
- Load from `hippo.yaml` config - adds coupling; config should be orthogonal

### D2: Database Connection Discovery
**Decision:** Use SQLite database at `data/hippo.db` (default) or path from environment variable `HIPPO_DB_PATH`.
**Rationale:** Follows existing storage adapter convention. Allows explicit override for testing/multi-db scenarios.
**Alternatives considered:**
- Always create new in-memory database - defeats the purpose of migration
- Query user for path - adds friction; CLI should be scriptable

### D3: Schema Diff Algorithm
**Decision:** Compare desired schema (from YAML) against actual database schema (queried from SQLite). Generate DDL for:
- New tables
- New columns on existing tables  
- New indexes
- New constraints
- New FTS tables

**Rationale:** Additive-only changes are safe for v0.1. The design document explicitly excludes destructive changes.
**Alternatives considered:**
- Full diff including deletions - too risky for v0.1; requires expand-contract convention enforcement
- Manual SQL migration files - doesn't integrate with schema-driven approach

### D4: Non-nullable Column Handling
**Decision:** If adding a NOT NULL column to a table with existing rows:
1. Check if column has a `default` value in schema
2. If yes, generate DDL with DEFAULT clause
3. If no, warn user and skip migration (require manual intervention)

**Rationale:** Safe default - prevents data loss. User can manually handle edge cases.
**Alternatives considered:**
- Auto-add DEFAULT 0/empty string - might not be semantically correct
- Fail hard - too strict; some migrations are safe

### D5: Preview Mode
**Decision:** `--preview` (alias `--dry-run`) outputs:
1. List of tables to be created/modified
2. DDL statements that would be executed
3. Warning messages for any potentially risky operations

Does not modify database.
**Rationale:** Standard convention. Allows CI/CD integration.
**Alternatives considered:**
- Only show summary - insufficient for debugging
- Interactive confirm mode - not scriptable

### D6: Schema Validation
**Decision:** Before generating migrations:
1. Validate all schema YAML files parse correctly
2. Check for conflicting definitions (same entity type defined multiple times)
3. Validate field types and references

Fail fast with clear error messages.
**Rationale:** Prevent invalid schemas from producing corrupt migrations.
**Alternatives considered:**
- Validate after migration - too late; might have partial changes
- Loose validation - risky; schema integrity is foundational

## Risks / Trade-offs

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Race condition with concurrent writes | Low | High | Document: require downtime or use exclusive lock during migration |
| Large table schema changes timeout | Medium | Medium | Use batched operations for backfill; add `--timeout` option |
| Schema drift between environments | Medium | Medium | Document: include schema files in version control; run migration in CI |
| FTS backfill slow on large datasets | Medium | Low | Existing batched backfill in `MigrationExecutor`; document performance |

## Migration Plan

1. **Update `hippo migrate` CLI** to load schemas and connect to database
2. **Implement `SchemaDiffEngine`** class that compares schemas
3. **Integrate with `MigrationPlanner`** to generate migration plans
4. **Add `--preview` flag** handling in CLI
5. **Add schema validation** before diff
6. **Add error handling** for edge cases (non-null without default, conflicts)

## Open Questions

- Q1: Should we track applied migrations in a table? (Deferred to v0.2 - currently uses restart-on-migrate pattern)
- Q2: How to handle schema changes to fields that affect FTS tables? (Will be covered by FTS migration logic in existing `FTSMigrationPlanner`)
- Q3: Should we support specifying schema directory path? (Consider adding `--schema-dir` option if needed)
