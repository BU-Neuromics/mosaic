"""PostgreSQL DDL generator.

Adapts the base DDL generator for PostgreSQL dialect:
- BOOLEAN instead of INTEGER for booleans
- DOUBLE PRECISION instead of REAL for floats
- JSONB for dict/list types
- TIMESTAMPTZ for datetime
- DATE for date
- Partial index WHERE clauses use TRUE/FALSE not 1/0
- FTS tables use tsvector/tsquery instead of FTS5 virtual tables
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from hippo.config.models import FieldDefinition, SchemaConfig
from hippo.core.storage.ddl_generator import (
    ColumnConstraint,
    ColumnDefinition,
    ForeignKeyDefinition,
    IndexDefinition,
    TableDefinition,
)


class PostgresDDLGenerator:
    """Generates PostgreSQL DDL statements from schema configs."""

    TYPE_MAPPING = {
        "string": "TEXT",
        "integer": "INTEGER",
        "float": "DOUBLE PRECISION",
        "boolean": "BOOLEAN",
        "date": "DATE",
        "datetime": "TIMESTAMPTZ",
        "list": "JSONB",
        "dict": "JSONB",
        "uri": "TEXT",
        "enum": "TEXT",
    }

    def __init__(self):
        self._table_definitions: dict[str, TableDefinition] = {}

    def generate(self, schemas: list[SchemaConfig]) -> list[str]:
        self._table_definitions = {}

        schema_map = {s.name: s for s in schemas}

        for schema in schemas:
            self._generate_table(schema, schema_map)

        ordered_tables = self._topological_sort()

        ddl_statements = []
        for table_name in ordered_tables:
            table = self._table_definitions[table_name]
            ddl_statements.append(self._generate_create_table(table))
            for index in table.indexes:
                ddl_statements.append(self._generate_create_index(table_name, index))

        return ddl_statements

    def _generate_table(
        self, schema: SchemaConfig, schema_map: dict[str, SchemaConfig]
    ) -> None:
        if schema.name in self._table_definitions:
            return

        for base_name in schema.get_bases():
            if base_name in schema_map:
                self._generate_table(schema_map[base_name], schema_map)

        table = TableDefinition(name=schema.name)

        table.columns.append(
            ColumnDefinition(
                name="id",
                column_type="TEXT",
                not_null=True,
                primary_key=True,
            )
        )

        for field_def in schema.fields:
            if field_def.name == "id":
                continue
            col = ColumnDefinition(
                name=field_def.name,
                column_type=self._map_type(field_def.type),
                not_null=field_def.required,
                default=field_def.default,
                primary_key=field_def.primary_key,
            )
            table.columns.append(col)

            if field_def.unique:
                table.unique_constraints.append([field_def.name])

            if field_def.index:
                index = IndexDefinition(
                    name=f"idx_{schema.name}_{field_def.name}",
                    columns=[field_def.name],
                    partial_where="is_available = TRUE",
                )
                table.indexes.append(index)

            if field_def.references:
                ref_table = field_def.references.get("table")
                ref_column = field_def.references.get("column", "id")
                on_delete = field_def.references.get("on_delete")
                if ref_table:
                    fk = ForeignKeyDefinition(
                        columns=[field_def.name],
                        references_table=ref_table,
                        references_columns=[ref_column],
                        on_delete=on_delete,
                    )
                    table.foreign_keys.append(fk)

        table.columns.append(
            ColumnDefinition(
                name="is_available",
                column_type="BOOLEAN",
                not_null=True,
                default=True,
            )
        )

        table.columns.append(
            ColumnDefinition(
                name="superseded_by",
                column_type="TEXT",
                not_null=False,
                default=None,
            )
        )

        if schema.unique_constraints:
            for constraint in schema.unique_constraints:
                table.unique_constraints.append(constraint)

        if schema.indexes:
            for idx_def in schema.indexes:
                idx = IndexDefinition(
                    name=idx_def.get(
                        "name",
                        f"idx_{schema.name}_{'_'.join(idx_def.get('columns', []))}",
                    ),
                    columns=idx_def.get("columns", []),
                    unique=idx_def.get("unique", False),
                    partial_where=idx_def.get("where", "is_available = TRUE")
                    if idx_def.get("partial")
                    else None,
                )
                table.indexes.append(idx)

        if schema.get_bases():
            for base_name in schema.get_bases():
                if base_name in schema_map:
                    fk = ForeignKeyDefinition(
                        columns=["id"],
                        references_table=base_name,
                        references_columns=["id"],
                        on_delete="CASCADE",
                    )
                    table.foreign_keys.append(fk)

        self._table_definitions[schema.name] = table

    def _map_type(self, field_type: str) -> str:
        return self.TYPE_MAPPING.get(field_type, "TEXT")

    def _topological_sort(self) -> list[str]:
        visited: set[str] = set()
        result: list[str] = []

        def visit(name: str) -> None:
            if name in visited:
                return
            visited.add(name)
            table = self._table_definitions.get(name)
            if table:
                for fk in table.foreign_keys:
                    if fk.references_table in self._table_definitions:
                        visit(fk.references_table)
            result.append(name)

        for name in self._table_definitions:
            visit(name)

        return result

    def _generate_create_table(self, table: TableDefinition) -> str:
        column_defs = []
        pk_cols = [c.name for c in table.columns if c.primary_key]

        for col in table.columns:
            col_def = f'"{col.name}" {col.column_type}'
            if col.primary_key and len(pk_cols) == 1:
                col_def += " PRIMARY KEY"
            if col.not_null and not col.primary_key:
                col_def += " NOT NULL"
            if col.default is not None:
                col_def += f" DEFAULT {self._format_default(col.default)}"
            column_defs.append(col_def)

        for fk in table.foreign_keys:
            fk_cols = ", ".join(f'"{c}"' for c in fk.columns)
            ref_cols = ", ".join(f'"{c}"' for c in fk.references_columns)
            fk_def = f'FOREIGN KEY ({fk_cols}) REFERENCES "{fk.references_table}"({ref_cols})'
            if fk.on_delete:
                fk_def += f" ON DELETE {fk.on_delete}"
            column_defs.append(fk_def)

        if pk_cols and len(pk_cols) > 1:
            pk_str = ", ".join(f'"{c}"' for c in pk_cols)
            column_defs.append(f"PRIMARY KEY ({pk_str})")

        for unique_cols in table.unique_constraints:
            unique_str = ", ".join(f'"{c}"' for c in unique_cols)
            column_defs.append(f"UNIQUE ({unique_str})")

        return (
            f'CREATE TABLE IF NOT EXISTS "{table.name}" (\n    '
            + ",\n    ".join(column_defs)
            + "\n);"
        )

    def _generate_create_index(self, table_name: str, index: IndexDefinition) -> str:
        columns_str = ", ".join(f'"{c}"' for c in index.columns)

        if index.partial_where:
            return f'CREATE INDEX IF NOT EXISTS "{index.name}" ON "{table_name}" ({columns_str}) WHERE {index.partial_where};'

        unique_str = "UNIQUE " if index.unique else ""
        return f'CREATE {unique_str}INDEX IF NOT EXISTS "{index.name}" ON "{table_name}" ({columns_str});'

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


class PostgresFTSMigrationPlanner:
    """Migration planner for PostgreSQL FTS tables.

    Creates regular tables with tsvector columns and GIN indexes
    instead of SQLite FTS5 virtual tables.
    """

    def __init__(self):
        self._fts_tables: dict[str, list[dict[str, str]]] = {}

    def add_schema(self, schema: SchemaConfig) -> None:
        fts_tables = []
        for field_def in schema.get_fts_fields():
            table_name = f"fts_{schema.name.lower()}_{field_def.name.lower()}"
            fts_tables.append(
                {
                    "table_name": table_name,
                    "entity_type": schema.name,
                    "field_name": field_def.name,
                }
            )
        if fts_tables:
            self._fts_tables[schema.name] = fts_tables

    def get_fts_tables_for_entity_type(
        self, entity_type: str
    ) -> list[dict[str, str]]:
        return self._fts_tables.get(entity_type, [])

    def get_all_fts_tables(self) -> dict[str, list[dict[str, str]]]:
        return self._fts_tables

    def generate_fts_ddl(self) -> list[str]:
        """Generate PostgreSQL FTS table DDL with tsvector and GIN indexes."""
        ddl_statements = []
        for entity_type, fts_tables in self._fts_tables.items():
            for fts_meta in fts_tables:
                table_name = fts_meta["table_name"]
                ddl_statements.append(
                    f"""CREATE TABLE IF NOT EXISTS "{table_name}" (
    "entity_id" TEXT NOT NULL PRIMARY KEY,
    "content" TEXT NOT NULL DEFAULT '',
    "content_tsvector" TSVECTOR
        GENERATED ALWAYS AS (to_tsvector('english', "content")) STORED
);"""
                )
                ddl_statements.append(
                    f'CREATE INDEX IF NOT EXISTS "idx_{table_name}_tsvector" '
                    f'ON "{table_name}" USING GIN ("content_tsvector");'
                )
                ddl_statements.append(
                    f'CREATE INDEX IF NOT EXISTS "idx_{table_name}_trigram" '
                    f'ON "{table_name}" USING GIN ("content" gin_trgm_ops);'
                )
        return ddl_statements
