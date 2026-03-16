"""Migration system for Hippo including FTS table support."""

import sqlite3
from dataclasses import dataclass
from typing import Any, Callable, Generator, Iterator, Optional

from hippo.config.models import FieldDefinition, SchemaConfig
from hippo.core.storage.ddl_generator import DDLGenerator, FTSMigrationPlanner
from hippo.core.storage.fts import FTSTableMetadata
from hippo.core.storage.schema_diff import SchemaDiff


@dataclass
class MigrationResult:
    """Result of a migration operation."""

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
    """Represents a migration plan."""

    def __init__(self):
        self.ddl_statements: list[str] = []
        self.alter_table_statements: list[str] = []
        self.create_index_statements: list[str] = []
        self.fts_ddl_statements: list[str] = []
        self.backfill_tasks: list[dict[str, Any]] = []
        self.warnings: list[str] = []
        self.new_tables: list[str] = []
        self.modified_tables: list[str] = []


class MigrationPlanner:
    """Plans migrations for schema changes."""

    def __init__(self):
        self._ddl_generator = DDLGenerator()
        self._fts_planner = FTSMigrationPlanner()
        self._existing_tables: set[str] = set()
        self._existing_fts_tables: set[str] = set()

    def load_existing_tables(self, cursor: sqlite3.Cursor) -> None:
        """Load existing tables from the database."""
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        self._existing_tables = {row[0] for row in cursor.fetchall()}

    def load_existing_fts_tables(self, cursor: sqlite3.Cursor) -> None:
        """Load existing FTS tables from the database."""
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'fts_%'"
        )
        self._existing_fts_tables = {row[0] for row in cursor.fetchall()}

    def plan_migration(self, schemas: list[SchemaConfig]) -> MigrationPlan:
        """Plan migration for given schemas."""
        plan = MigrationPlan()

        ddl_statements = self._ddl_generator.generate(schemas)
        plan.ddl_statements = ddl_statements

        for schema in schemas:
            self._fts_planner.add_schema(schema)

        plan.fts_ddl_statements = self._fts_planner.generate_fts_ddl()

        for entity_type, fts_tables in self._fts_planner.get_all_fts_tables().items():
            for fts_metadata in fts_tables:
                if fts_metadata.table_name not in self._existing_fts_tables:
                    plan.backfill_tasks.append(
                        {
                            "entity_type": entity_type,
                            "fts_table": fts_metadata.table_name,
                            "fields": fts_metadata.get_fts_columns(),
                        }
                    )

        return plan

    def plan_migration_from_diff(
        self,
        schema_diff: SchemaDiff,
        schemas: list[SchemaConfig],
        cursor: sqlite3.Cursor,
    ) -> MigrationPlan:
        """Plan migration from schema diff output.

        Args:
            schema_diff: The schema diff computed by SchemaDiffEngine
            schemas: List of schema configurations
            cursor: Database cursor for checking existing data

        Returns:
            MigrationPlan with statements for all detected changes
        """
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
                    for fts_metadata in fts_tables:
                        if fts_metadata.table_name not in self._existing_fts_tables:
                            plan.backfill_tasks.append(
                                {
                                    "entity_type": entity_type,
                                    "fts_table": fts_metadata.table_name,
                                    "fields": fts_metadata.get_fts_columns(),
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
        """Generate ALTER TABLE statement for adding a new column."""
        col_type = DDLGenerator.TYPE_MAPPING.get(field_def.type, "TEXT")
        col_def = f'ALTER TABLE "{table_name}" ADD COLUMN "{field_def.name}" {col_type}'

        if field_def.required:
            col_def += " NOT NULL"
            if field_def.default is not None:
                col_def += f" DEFAULT {self._format_default(field_def.default)}"

        return col_def + ";"

    def _generate_create_index(self, table_name: str, index_def: dict[str, Any]) -> str:
        """Generate CREATE INDEX statement."""
        index_name = index_def.get(
            "name", f"idx_{table_name}_{'_'.join(index_def.get('columns', []))}"
        )
        columns = index_def.get("columns", [])
        columns_str = ", ".join(f'"{c}"' for c in columns)

        unique_str = "UNIQUE " if index_def.get("unique", False) else ""

        if index_def.get("where"):
            return f'CREATE {unique_str}INDEX "{index_name}" ON "{table_name}" ({columns_str}) WHERE {index_def.get("where")};'

        return f'CREATE {unique_str}INDEX "{index_name}" ON "{table_name}" ({columns_str});'

    def _format_default(self, default: Any) -> str:
        """Format default value for SQL."""
        if default is None:
            return "NULL"
        elif isinstance(default, bool):
            return "1" if default else "0"
        elif isinstance(default, str):
            return f"'{default}'"
        elif isinstance(default, (int, float)):
            return str(default)
        else:
            return f"'{str(default)}'"


class MigrationExecutor:
    """Executes migrations."""

    def __init__(self, connection: sqlite3.Connection):
        self._conn = connection

    def execute_migration(self, plan: MigrationPlan) -> MigrationResult:
        """Execute a migration plan."""
        cursor = self._conn.cursor()
        tables_created = []
        fts_tables_created = []
        records_backfilled = 0
        errors = []

        try:
            for ddl in plan.ddl_statements:
                table_name = self._extract_table_name(ddl)
                if table_name:
                    cursor.execute(ddl)
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
                table_name = self._extract_fts_table_name(fts_ddl)
                if table_name:
                    cursor.execute(fts_ddl)
                    fts_tables_created.append(table_name)

            for task in plan.backfill_tasks:
                try:
                    count = self._backfill_fts_table(cursor, task)
                    records_backfilled += count
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
        """Backfill an FTS table with existing data.

        If the source ``entities`` table does not yet exist (e.g. fresh schema
        creation in a test fixture or brand-new deployment) the backfill is a
        no-op and returns 0.
        """
        entity_type = task["entity_type"]
        fts_table = task["fts_table"]
        fields = task["fields"]

        # Guard: skip backfill if the entities table hasn't been created yet.
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='entities'"
        )
        if not cursor.fetchone():
            return 0

        cursor.execute(
            "SELECT id, data FROM entities WHERE entity_type = ? AND is_available = 1",
            (entity_type,),
        )

        count = 0
        for row in cursor.fetchall():
            entity_id = row["id"]
            data = row["data"]
            if isinstance(data, str):
                import json

                data = json.loads(data)

            content_parts = []
            for field in fields:
                if field in data:
                    content_parts.append(str(data[field]))

            if content_parts:
                content = " ".join(content_parts)
                cursor.execute(
                    f"INSERT INTO {fts_table} (entity_id, content) VALUES (?, ?)",
                    (entity_id, content),
                )
                count += 1

        return count

    def _extract_table_name(self, ddl: str) -> Optional[str]:
        """Extract table name from CREATE TABLE statement."""
        import re

        match = re.search(r'CREATE TABLE "?(\w+)"?', ddl, re.IGNORECASE)
        return match.group(1) if match else None

    def _extract_fts_table_name(self, ddl: str) -> Optional[str]:
        """Extract FTS table name from CREATE VIRTUAL TABLE statement."""
        import re

        match = re.search(r"USING fts5\([^)]+\)", ddl, re.IGNORECASE)
        if match:
            table_match = re.search(r'"?(\w+)"?', ddl[: match.start()])
            return table_match.group(1) if table_match else None
        return None


def batched(iterable: list[Any], batch_size: int) -> Generator[list[Any], None, None]:
    """Yield successive batches from an iterable."""
    for i in range(0, len(iterable), batch_size):
        yield iterable[i : i + batch_size]
