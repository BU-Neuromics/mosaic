"""PostgreSQL migration system using LinkML-backed SchemaRegistry."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from linkml_runtime.linkml_model.meta import SlotDefinition

from hippo.core.storage.migration import MigrationPlan, MigrationResult
from hippo.core.storage.pg_ddl_generator import (
    PostgresDDLGenerator,
    PostgresFTSMigrationPlanner,
)
from hippo.core.storage.schema_diff import SchemaDiff
from hippo.linkml_bridge import SchemaRegistry, annotation_value, slot_default

try:
    import psycopg
except ImportError:
    raise ImportError(
        "PostgreSQL migration requires psycopg. "
        "Install with: pip install hippo[postgres]"
    )


class PostgresMigrationPlanner:
    def __init__(self) -> None:
        self._ddl_generator = PostgresDDLGenerator()
        self._fts_planner = PostgresFTSMigrationPlanner()
        self._existing_tables: set[str] = set()
        self._existing_fts_tables: set[str] = set()

    def load_existing_tables(self, cur: psycopg.Cursor) -> None:
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        self._existing_tables = {row["tablename"] for row in cur.fetchall()}

    def load_existing_fts_tables(self, cur: psycopg.Cursor) -> None:
        cur.execute(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename LIKE 'fts_%'"
        )
        self._existing_fts_tables = {row["tablename"] for row in cur.fetchall()}

    def plan_migration(self, registry: SchemaRegistry) -> MigrationPlan:
        plan = MigrationPlan()
        plan.ddl_statements = self._ddl_generator.generate(registry)
        self._fts_planner.add_registry(registry)
        plan.fts_ddl_statements = self._fts_planner.generate_fts_ddl()
        for entity_type, entries in self._fts_planner.get_all_fts_tables().items():
            for entry in entries:
                if entry["table_name"] not in self._existing_fts_tables:
                    plan.backfill_tasks.append(
                        {
                            "entity_type": entity_type,
                            "fts_table": entry["table_name"],
                            "field_name": entry["field_name"],
                        }
                    )
        return plan

    def plan_migration_from_diff(
        self,
        schema_diff: SchemaDiff,
        registry: SchemaRegistry,
        cur: psycopg.Cursor,
    ) -> MigrationPlan:
        plan = MigrationPlan()
        for class_name in schema_diff.new_tables:
            self._ddl_generator._build_table(registry, class_name)
        for class_name in schema_diff.new_tables:
            table = self._ddl_generator._tables.get(class_name)
            if table is None:
                continue
            plan.ddl_statements.append(
                self._ddl_generator._render_create_table(table)
            )
            for index in table.indexes:
                plan.ddl_statements.append(
                    self._ddl_generator._render_create_index(class_name, index)
                )
            plan.new_tables.append(class_name)
            self._fts_planner.add_class(registry, class_name)

        plan.fts_ddl_statements.extend(self._fts_planner.generate_fts_ddl())

        for entity_type, entries in self._fts_planner.get_all_fts_tables().items():
            for entry in entries:
                if entry["table_name"] not in self._existing_fts_tables:
                    plan.backfill_tasks.append(
                        {
                            "entity_type": entity_type,
                            "fts_table": entry["table_name"],
                            "field_name": entry["field_name"],
                        }
                    )

        for table_name, new_slots in schema_diff.new_columns.items():
            for slot in new_slots:
                alter = self._alter_table_add_column(registry, table_name, slot)
                if alter:
                    plan.alter_table_statements.append(alter)
                    if table_name not in plan.modified_tables:
                        plan.modified_tables.append(table_name)

        for table_name, new_indexes in schema_diff.new_indexes.items():
            for idx in new_indexes:
                plan.create_index_statements.append(
                    self._create_index_statement(table_name, idx)
                )

        plan.warnings.extend(schema_diff.warnings)
        return plan

    def _alter_table_add_column(
        self, registry: SchemaRegistry, table_name: str, slot: SlotDefinition
    ) -> Optional[str]:
        known = set(registry.class_names())
        rng = slot.range
        col_type = (
            "TEXT"
            if rng in known or rng is None
            else PostgresDDLGenerator.TYPE_MAPPING.get(rng, "TEXT")
        )
        sql = (
            f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS '
            f'"{slot.name}" {col_type}'
        )
        if slot.required:
            sql += " NOT NULL"
            default = slot_default(slot)
            if default is not None:
                sql += f" DEFAULT {PostgresDDLGenerator._format_default(default)}"
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
                f'CREATE {unique}INDEX IF NOT EXISTS "{name}" ON "{table_name}" '
                f"({columns}) WHERE {where};"
            )
        return (
            f'CREATE {unique}INDEX IF NOT EXISTS "{name}" '
            f'ON "{table_name}" ({columns});'
        )


class PostgresMigrationExecutor:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def execute_migration(self, plan: MigrationPlan) -> MigrationResult:
        cur = self._conn.cursor()
        tables_created: list[str] = []
        fts_tables_created: list[str] = []
        records_backfilled = 0
        errors: list[str] = []

        try:
            for ddl in plan.ddl_statements:
                cur.execute(ddl)
                table_name = _extract_table_name(ddl)
                if table_name:
                    tables_created.append(table_name)

            for alter_stmt in plan.alter_table_statements:
                try:
                    cur.execute(alter_stmt)
                except psycopg.Error as e:
                    errors.append(f"ALTER TABLE error: {e}")

            for index_stmt in plan.create_index_statements:
                try:
                    cur.execute(index_stmt)
                except psycopg.Error as e:
                    errors.append(f"CREATE INDEX error: {e}")

            for fts_ddl in plan.fts_ddl_statements:
                cur.execute(fts_ddl)
                table_name = _extract_table_name(fts_ddl)
                if table_name:
                    fts_tables_created.append(table_name)

            for task in plan.backfill_tasks:
                try:
                    records_backfilled += self._backfill_fts_table(cur, task)
                except Exception as e:
                    errors.append(f"Backfill error for {task['fts_table']}: {e}")

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

    def _backfill_fts_table(self, cur: psycopg.Cursor, task: dict[str, Any]) -> int:
        entity_type = task["entity_type"]
        fts_table = task["fts_table"]
        field_name = task.get("field_name")

        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' "
            "AND tablename = 'entities')"
        )
        if not cur.fetchone()["exists"]:
            return 0

        cur.execute(
            "SELECT id, data FROM entities WHERE entity_type = %s AND is_available = TRUE",
            (entity_type,),
        )

        count = 0
        for row in cur.fetchall():
            entity_id = row["id"]
            data = row["data"]
            if isinstance(data, str):
                data = json.loads(data)

            content = ""
            if field_name and field_name in data:
                content = str(data[field_name])
            elif data:
                content = " ".join(str(v) for v in data.values() if v)

            if content:
                cur.execute(
                    f"""INSERT INTO "{fts_table}" (entity_id, content)
                        VALUES (%s, %s)
                        ON CONFLICT (entity_id) DO UPDATE SET content = EXCLUDED.content""",
                    (entity_id, content),
                )
                count += 1
        return count


def _extract_table_name(ddl: str) -> Optional[str]:
    match = re.search(
        r'CREATE TABLE(?:\s+IF NOT EXISTS)?\s+"?(\w+)"?', ddl, re.IGNORECASE
    )
    return match.group(1) if match else None
