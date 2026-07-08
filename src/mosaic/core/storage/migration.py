"""Migration system for Mosaic including FTS table support.

Operates on a ``SchemaRegistry`` (LinkML-backed) and plans DDL against the
current SQLite database state, then executes the plan.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Generator, Optional

from linkml_runtime.linkml_model.meta import SlotDefinition

from mosaic.core.storage.ddl_generator import DDLGenerator, FTSMigrationPlanner
from mosaic.core.storage.schema_diff import SchemaDiff
from mosaic.linkml_bridge import SchemaRegistry, slot_default


@dataclass
class MigrationResult:
    success: bool
    tables_created: list[str]
    tables_modified: Optional[list[str]] = None
    fts_tables_created: Optional[list[str]] = None
    records_backfilled: int = 0
    errors: Optional[list[str]] = None
    warnings: Optional[list[str]] = None

    def __post_init__(self):
        if self.tables_modified is None:
            self.tables_modified = []
        if self.fts_tables_created is None:
            self.fts_tables_created = []
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


class MigrationPlan:
    def __init__(self) -> None:
        self.ddl_statements: list[str] = []
        self.alter_table_statements: list[str] = []
        self.create_index_statements: list[str] = []
        self.fts_ddl_statements: list[str] = []
        self.backfill_tasks: list[dict[str, Any]] = []
        self.warnings: list[str] = []
        self.new_tables: list[str] = []
        self.modified_tables: list[str] = []


class MigrationPlanner:
    def __init__(self) -> None:
        self._ddl_generator = DDLGenerator()
        self._fts_planner = FTSMigrationPlanner()
        self._existing_fts_tables: set[str] = set()

    def load_existing_fts_tables(self, cursor: sqlite3.Cursor) -> None:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'fts_%'"
        )
        self._existing_fts_tables = {row[0] for row in cursor.fetchall()}

    def plan_migration(self, registry: SchemaRegistry) -> MigrationPlan:
        plan = MigrationPlan()
        plan.ddl_statements = self._ddl_generator.generate(registry)
        self._fts_planner.add_registry(registry)
        plan.fts_ddl_statements = self._fts_planner.generate_fts_ddl()
        plan.backfill_tasks = self._build_backfill_tasks()
        return plan

    def plan_migration_from_diff(
        self,
        schema_diff: SchemaDiff,
        registry: SchemaRegistry,
        cursor: sqlite3.Cursor,
    ) -> MigrationPlan:
        plan = MigrationPlan()

        if schema_diff.new_tables:
            new_tables_set = set(schema_diff.new_tables)
            # Generate full registry DDL via the LinkML-backed generator,
            # then keep only statements owned by tables in the diff. FTS
            # virtual tables are emitted by ``DDLGenerator.generate`` too,
            # but we skip them here and re-emit via ``_fts_planner`` so
            # the planner state stays consistent with backfill bookkeeping.
            for stmt in self._ddl_generator.generate(registry):
                if "CREATE VIRTUAL TABLE" in stmt:
                    continue
                owner = _ddl_owner_table(stmt)
                if owner is not None and owner in new_tables_set:
                    plan.ddl_statements.append(stmt)
            plan.new_tables.extend(schema_diff.new_tables)

            for class_name in schema_diff.new_tables:
                self._fts_planner.add_class(registry, class_name)
            plan.fts_ddl_statements.extend(self._fts_planner.generate_fts_ddl())
            plan.backfill_tasks.extend(self._build_backfill_tasks())

        for table_name, new_slots in schema_diff.new_columns.items():
            for slot in new_slots:
                alter = self._alter_table_add_column(registry, table_name, slot)
                if alter:
                    plan.alter_table_statements.append(alter)
                    if table_name not in plan.modified_tables:
                        plan.modified_tables.append(table_name)

        for table_name, new_indexes in schema_diff.new_indexes.items():
            for idx in new_indexes:
                stmt = self._create_index_statement(table_name, idx)
                if stmt:
                    plan.create_index_statements.append(stmt)

        plan.warnings.extend(schema_diff.warnings)
        return plan

    def _build_backfill_tasks(self) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = []
        for entity_type, fts_tables in self._fts_planner.get_all_fts_tables().items():
            for meta in fts_tables:
                if meta.table_name not in self._existing_fts_tables:
                    tasks.append(
                        {
                            "entity_type": entity_type,
                            "fts_table": meta.table_name,
                            "fields": meta.get_fts_columns(),
                        }
                    )
        return tasks

    def _alter_table_add_column(
        self, registry: SchemaRegistry, table_name: str, slot: SlotDefinition
    ) -> Optional[str]:
        known = set(registry.class_names())
        rng = slot.range
        if rng and rng in known:
            col_type = "TEXT"
        elif rng:
            col_type = DDLGenerator.TYPE_MAPPING.get(rng, "TEXT")
        else:
            col_type = "TEXT"
        sql = f'ALTER TABLE "{table_name}" ADD COLUMN "{slot.name}" {col_type}'
        if slot.required:
            sql += " NOT NULL"
            default = slot_default(slot)
            if default is not None:
                sql += f" DEFAULT {DDLGenerator._format_default(default)}"
        return sql + ";"

    def _create_index_statement(
        self, table_name: str, index_def: dict[str, Any]
    ) -> str:
        name = index_def.get(
            "name", f"idx_{table_name}_{'_'.join(index_def.get('columns', []))}"
        )
        columns = ", ".join(f'"{c}"' for c in index_def.get("columns", []))
        unique = "UNIQUE " if index_def.get("unique") else ""
        where = index_def.get("where")
        if where:
            return (
                f'CREATE {unique}INDEX "{name}" ON "{table_name}" ({columns}) '
                f"WHERE {where};"
            )
        return f'CREATE {unique}INDEX "{name}" ON "{table_name}" ({columns});'


class MigrationExecutor:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    def execute_migration(self, plan: MigrationPlan) -> MigrationResult:
        cursor = self._conn.cursor()
        tables_created: list[str] = []
        fts_tables_created: list[str] = []
        records_backfilled = 0
        errors: list[str] = []

        try:
            for ddl in plan.ddl_statements:
                cursor.execute(ddl)
                table_name = _extract_table_name(ddl)
                if table_name:
                    tables_created.append(table_name)

            for alter_stmt in plan.alter_table_statements:
                try:
                    cursor.execute(alter_stmt)
                except sqlite3.Error as e:
                    errors.append(f"ALTER TABLE error: {e}")

            for index_stmt in plan.create_index_statements:
                try:
                    cursor.execute(index_stmt)
                except sqlite3.Error as e:
                    errors.append(f"CREATE INDEX error: {e}")

            for fts_ddl in plan.fts_ddl_statements:
                table_name = _extract_fts_table_name(fts_ddl)
                if table_name:
                    cursor.execute(fts_ddl)
                    fts_tables_created.append(table_name)

            for task in plan.backfill_tasks:
                try:
                    records_backfilled += self._backfill_fts_table(cursor, task)
                except Exception as e:
                    errors.append(f"Backfill error for {task['fts_table']}: {str(e)}")

        except Exception as e:
            errors.append(str(e))

        return MigrationResult(
            success=len(errors) == 0,
            tables_created=tables_created,
            tables_modified=plan.modified_tables,
            fts_tables_created=fts_tables_created,
            records_backfilled=records_backfilled,
            errors=errors,
            warnings=plan.warnings,
        )

    def _backfill_fts_table(self, cursor: sqlite3.Cursor, task: dict[str, Any]) -> int:
        entity_type = task["entity_type"]
        fts_table = task["fts_table"]
        fields = task["fields"]

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            (entity_type,),
        )
        if not cursor.fetchone():
            return 0

        # Per-class typed tables expose each FTS-indexed slot as a real
        # column; project them directly instead of decoding a JSON blob.
        select_cols = ", ".join(f'"{f}"' for f in fields)
        cursor.execute(
            f'SELECT id, {select_cols} FROM "{entity_type}" WHERE is_available = 1',
        )

        count = 0
        for row in cursor.fetchall():
            entity_id = row["id"]
            content_parts = [str(row[f]) for f in fields if row[f] is not None]
            if content_parts:
                cursor.execute(
                    f"INSERT INTO {fts_table} (entity_id, content) VALUES (?, ?)",
                    (entity_id, " ".join(content_parts)),
                )
                count += 1
        return count


def _extract_table_name(ddl: str) -> Optional[str]:
    import re

    match = re.search(r'CREATE TABLE "?(\w+)"?', ddl, re.IGNORECASE)
    return match.group(1) if match else None


def _ddl_owner_table(stmt: str) -> Optional[str]:
    """Return the table a CREATE statement targets, or None.

    Recognizes ``CREATE TABLE "name"``, ``CREATE [UNIQUE] INDEX … ON "table"``,
    and ``CREATE TRIGGER … ON "table"`` (triggers may span lines, so use
    DOTALL). Returns None for FTS virtual tables and any unrecognized form.
    """
    import re

    m = re.search(
        r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"?(\w+)"?',
        stmt,
        re.IGNORECASE,
    )
    if m:
        return m.group(1)
    m = re.search(
        r'CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?"[^"]+"\s+ON\s+"([^"]+)"',
        stmt,
        re.IGNORECASE,
    )
    if m:
        return m.group(1)
    m = re.search(
        r'CREATE\s+TRIGGER\s+"[^"]+"\s+(?:BEFORE|AFTER|INSTEAD\s+OF)\s+\w+\s+ON\s+"([^"]+)"',
        stmt,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        return m.group(1)
    return None


def _extract_fts_table_name(ddl: str) -> Optional[str]:
    import re

    match = re.search(r"CREATE VIRTUAL TABLE(?:\s+IF NOT EXISTS)?\s+(\w+)", ddl, re.IGNORECASE)
    return match.group(1) if match else None


def batched(iterable: list[Any], batch_size: int) -> Generator[list[Any], None, None]:
    for i in range(0, len(iterable), batch_size):
        yield iterable[i : i + batch_size]
