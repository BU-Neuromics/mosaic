"""PostgreSQL migration system for Hippo.

Mirrors the SQLite migration module but uses PostgreSQL-specific DDL,
psycopg3 connections, and PostgreSQL FTS (tsvector) instead of FTS5.
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

from hippo.config.models import FieldDefinition, SchemaConfig
from hippo.core.storage.migration import MigrationPlan, MigrationResult
from hippo.core.storage.pg_ddl_generator import (
    PostgresDDLGenerator,
    PostgresFTSMigrationPlanner,
)
from hippo.core.storage.schema_diff import SchemaDiff

try:
    import psycopg
except ImportError:
    raise ImportError(
        "PostgreSQL migration requires psycopg. "
        "Install with: pip install hippo[postgres]"
    )


class PostgresMigrationPlanner:
    """Plans migrations for PostgreSQL schema changes."""

    def __init__(self):
        self._ddl_generator = PostgresDDLGenerator()
        self._fts_planner = PostgresFTSMigrationPlanner()
        self._existing_tables: set[str] = set()
        self._existing_fts_tables: set[str] = set()

    def load_existing_tables(self, cur: psycopg.Cursor) -> None:
        cur.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
        self._existing_tables = {row["tablename"] for row in cur.fetchall()}

    def load_existing_fts_tables(self, cur: psycopg.Cursor) -> None:
        cur.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE 'fts_%'"
        )
        self._existing_fts_tables = {row["tablename"] for row in cur.fetchall()}

    def plan_migration(self, schemas: list[SchemaConfig]) -> MigrationPlan:
        plan = MigrationPlan()

        ddl_statements = self._ddl_generator.generate(schemas)
        plan.ddl_statements = ddl_statements

        for schema in schemas:
            self._fts_planner.add_schema(schema)

        plan.fts_ddl_statements = self._fts_planner.generate_fts_ddl()

        for entity_type, fts_tables in self._fts_planner.get_all_fts_tables().items():
            for fts_meta in fts_tables:
                if fts_meta["table_name"] not in self._existing_fts_tables:
                    plan.backfill_tasks.append(
                        {
                            "entity_type": entity_type,
                            "fts_table": fts_meta["table_name"],
                            "field_name": fts_meta["field_name"],
                        }
                    )

        return plan

    def plan_migration_from_diff(
        self,
        schema_diff: SchemaDiff,
        schemas: list[SchemaConfig],
        cur: psycopg.Cursor,
    ) -> MigrationPlan:
        plan = MigrationPlan()
        schema_map = {s.name: s for s in schemas}

        for schema in schema_diff.new_tables:
            if schema.name in schema_map:
                table_ddl = self._ddl_generator.generate([schema_map[schema.name]])
                plan.ddl_statements.extend(table_ddl)
                plan.new_tables.append(schema.name)

                self._fts_planner.add_schema(schema)
                fts_ddl = self._fts_planner.generate_fts_ddl()
                plan.fts_ddl_statements.extend(fts_ddl)

                for (
                    entity_type,
                    fts_tables,
                ) in self._fts_planner.get_all_fts_tables().items():
                    for fts_meta in fts_tables:
                        if fts_meta["table_name"] not in self._existing_fts_tables:
                            plan.backfill_tasks.append(
                                {
                                    "entity_type": entity_type,
                                    "fts_table": fts_meta["table_name"],
                                    "field_name": fts_meta["field_name"],
                                }
                            )

        for table_name, new_columns in schema_diff.new_columns.items():
            for col in new_columns:
                alter_stmt = self._generate_alter_table_add_column(table_name, col)
                if alter_stmt:
                    plan.alter_table_statements.append(alter_stmt)
                    if table_name not in plan.modified_tables:
                        plan.modified_tables.append(table_name)

        for table_name, new_indexes in schema_diff.new_indexes.items():
            for idx in new_indexes:
                index_stmt = self._generate_create_index(table_name, idx)
                if index_stmt:
                    plan.create_index_statements.append(index_stmt)

        plan.warnings.extend(schema_diff.warnings)
        return plan

    def _generate_alter_table_add_column(
        self, table_name: str, field_def: FieldDefinition
    ) -> Optional[str]:
        col_type = PostgresDDLGenerator.TYPE_MAPPING.get(field_def.type, "TEXT")
        col_def = f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS "{field_def.name}" {col_type}'

        if field_def.required:
            col_def += " NOT NULL"
            if field_def.default is not None:
                col_def += f" DEFAULT {self._format_default(field_def.default)}"

        return col_def + ";"

    def _generate_create_index(
        self, table_name: str, index_def: dict[str, Any]
    ) -> str:
        index_name = index_def.get(
            "name", f"idx_{table_name}_{'_'.join(index_def.get('columns', []))}"
        )
        columns = index_def.get("columns", [])
        columns_str = ", ".join(f'"{c}"' for c in columns)

        unique_str = "UNIQUE " if index_def.get("unique", False) else ""

        if index_def.get("where"):
            return f'CREATE {unique_str}INDEX IF NOT EXISTS "{index_name}" ON "{table_name}" ({columns_str}) WHERE {index_def.get("where")};'

        return f'CREATE {unique_str}INDEX IF NOT EXISTS "{index_name}" ON "{table_name}" ({columns_str});'

    def _format_default(self, default: Any) -> str:
        if default is None:
            return "NULL"
        elif isinstance(default, bool):
            return "TRUE" if default else "FALSE"
        elif isinstance(default, str):
            return f"'{default}'"
        elif isinstance(default, (int, float)):
            return str(default)
        else:
            return f"'{str(default)}'"


class PostgresMigrationExecutor:
    """Executes migrations against PostgreSQL."""

    def __init__(self, conn: psycopg.Connection):
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
                table_name = self._extract_table_name(ddl)
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
                table_name = self._extract_table_name(fts_ddl)
                if table_name:
                    fts_tables_created.append(table_name)

            for task in plan.backfill_tasks:
                try:
                    count = self._backfill_fts_table(cur, task)
                    records_backfilled += count
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

    def _backfill_fts_table(
        self, cur: psycopg.Cursor, task: dict[str, Any]
    ) -> int:
        entity_type = task["entity_type"]
        fts_table = task["fts_table"]
        field_name = task.get("field_name")

        # Check entities table exists
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'entities')"
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

    def _extract_table_name(self, ddl: str) -> Optional[str]:
        match = re.search(r'CREATE TABLE(?:\s+IF NOT EXISTS)?\s+"?(\w+)"?', ddl, re.IGNORECASE)
        return match.group(1) if match else None
