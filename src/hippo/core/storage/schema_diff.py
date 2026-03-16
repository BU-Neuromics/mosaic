"""Schema diff engine for detecting additive changes between schemas and database."""

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from hippo.config.models import FieldDefinition, SchemaConfig


@dataclass
class TableMetadata:
    """Metadata for an existing database table."""

    name: str
    columns: list[dict[str, Any]] = field(default_factory=list)
    indexes: list[dict[str, Any]] = field(default_factory=list)
    foreign_keys: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SchemaDiff:
    """Represents the difference between desired and current schema."""

    new_tables: list[SchemaConfig] = field(default_factory=list)
    new_columns: dict[str, list[FieldDefinition]] = field(default_factory=dict)
    new_indexes: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    new_constraints: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class SchemaValidationError(Exception):
    """Exception raised for schema validation errors."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Schema validation failed: {'; '.join(errors)}")


class SchemaValidator:
    """Validator for schema definitions."""

    VALID_FIELD_TYPES = {
        "string",
        "integer",
        "float",
        "boolean",
        "date",
        "datetime",
        "list",
        "dict",
        "uri",
        "enum",
    }

    def __init__(self):
        self._errors: list[str] = []

    def validate(self, schemas: list[SchemaConfig]) -> None:
        """Validate all schemas.

        Raises:
            SchemaValidationError: If any validation errors are found
        """
        self._errors = []
        schema_names = set()

        for schema in schemas:
            self._validate_duplicate(schema, schema_names)
            self._validate_field_types(schema)
            self._validate_references(schema, schemas)

        if self._errors:
            raise SchemaValidationError(self._errors)

    def _validate_duplicate(self, schema: SchemaConfig, schema_names: set[str]) -> None:
        """Check for duplicate entity type definitions."""
        if schema.name in schema_names:
            self._errors.append(f"Duplicate entity type definition: {schema.name}")
        schema_names.add(schema.name)

    def _validate_field_types(self, schema: SchemaConfig) -> None:
        """Validate field types."""
        for field_def in schema.fields:
            if field_def.type not in self.VALID_FIELD_TYPES:
                self._errors.append(
                    f"Invalid field type '{field_def.type}' in entity '{schema.name}', field '{field_def.name}'. "
                    f"Must be one of: {', '.join(sorted(self.VALID_FIELD_TYPES))}"
                )

    def _validate_references(
        self, schema: SchemaConfig, all_schemas: list[SchemaConfig]
    ) -> None:
        """Validate that referenced entity types exist."""
        schema_names = {s.name for s in all_schemas}

        for field_def in schema.fields:
            if field_def.references:
                ref_table = field_def.references.get("table")
                if ref_table and ref_table not in schema_names:
                    self._errors.append(
                        f"Broken reference in entity '{schema.name}', field '{field_def.name}': "
                        f"references non-existent entity type '{ref_table}'"
                    )


class SchemaDiffEngine:
    """Engine for computing schema differences between YAML definitions and database."""

    TYPE_MAPPING = {
        "string": "TEXT",
        "integer": "INTEGER",
        "float": "REAL",
        "boolean": "INTEGER",
        "date": "TEXT",
        "datetime": "TEXT",
        "list": "TEXT",
        "dict": "TEXT",
        "uri": "TEXT",
        "enum": "TEXT",
    }

    def __init__(self, cursor: Optional[sqlite3.Cursor] = None):
        self._existing_tables: dict[str, TableMetadata] = {}
        self._schema_configs: dict[str, SchemaConfig] = {}
        self._cursor = cursor

    def set_cursor(self, cursor: sqlite3.Cursor) -> None:
        """Set the cursor for database operations."""
        self._cursor = cursor

    def load_existing_schema(self, cursor: sqlite3.Cursor) -> None:
        """Load existing table metadata from SQLite."""
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'fts_%'"
        )
        table_names = [row[0] for row in cursor.fetchall()]

        for table_name in table_names:
            table_meta = TableMetadata(name=table_name)

            cursor.execute(f"PRAGMA table_info('{table_name}')")
            table_meta.columns = [
                {
                    "name": row[1],
                    "type": row[2],
                    "not_null": bool(row[3]),
                    "default": row[4],
                    "primary_key": bool(row[5]),
                }
                for row in cursor.fetchall()
            ]

            cursor.execute(f"PRAGMA index_list('{table_name}')")
            table_meta.indexes = [
                {"name": row[1], "unique": bool(row[2]), "origin": row[3]}
                for row in cursor.fetchall()
            ]

            cursor.execute(f"PRAGMA foreign_key_list('{table_name}')")
            table_meta.foreign_keys = [
                {
                    "table": row[2],
                    "from": row[3],
                    "to": row[4],
                    "on_delete": row[5],
                }
                for row in cursor.fetchall()
            ]

            self._existing_tables[table_name] = table_meta

    def load_schemas_from_files(self, schema_dir: Path) -> list[SchemaConfig]:
        """Load schema definitions from YAML files in the given directory."""
        if not schema_dir.exists():
            return []

        schema_files = list(schema_dir.glob("*.yaml")) + list(schema_dir.glob("*.yml"))

        schemas = []
        for schema_file in schema_files:
            try:
                content = yaml.safe_load(schema_file.read_text())
                if content:
                    schema = SchemaConfig.from_dict(content)
                    self._schema_configs[schema.name] = schema
                    schemas.append(schema)
            except Exception as e:
                raise ValueError(f"Failed to load schema from {schema_file}: {e}")

        return schemas

    def compute_diff(self, schemas: list[SchemaConfig]) -> SchemaDiff:
        """Compute the difference between desired schemas and existing database."""
        diff = SchemaDiff()

        for schema in schemas:
            if schema.name not in self._existing_tables:
                diff.new_tables.append(schema)
            else:
                existing_table = self._existing_tables[schema.name]
                self._compute_column_diff(schema, existing_table, diff)
                self._compute_index_diff(schema, existing_table, diff)
                self._compute_constraint_diff(schema, existing_table, diff)

        return diff

    def _compute_column_diff(
        self,
        schema: SchemaConfig,
        existing_table: TableMetadata,
        diff: SchemaDiff,
    ) -> None:
        """Compute differences in columns between schema and existing table."""
        existing_columns = {col["name"] for col in existing_table.columns}

        for field_def in schema.fields:
            if field_def.name not in existing_columns:
                if schema.name not in diff.new_columns:
                    diff.new_columns[schema.name] = []
                diff.new_columns[schema.name].append(field_def)

                if field_def.required:
                    has_default = field_def.default is not None
                    table_has_data = self._table_has_data(schema.name)

                    if table_has_data and not has_default:
                        diff.warnings.append(
                            f"Adding NOT NULL column '{field_def.name}' to table '{schema.name}' "
                            f"with existing data but no default value defined"
                        )

    def _compute_index_diff(
        self,
        schema: SchemaConfig,
        existing_table: TableMetadata,
        diff: SchemaDiff,
    ) -> None:
        """Compute differences in indexes between schema and existing table."""
        existing_index_names = {idx["name"] for idx in existing_table.indexes}

        for field_def in schema.fields:
            if field_def.index:
                index_name = f"idx_{schema.name}_{field_def.name}"
                if index_name not in existing_index_names:
                    if schema.name not in diff.new_indexes:
                        diff.new_indexes[schema.name] = []
                    diff.new_indexes[schema.name].append(
                        {
                            "name": index_name,
                            "columns": [field_def.name],
                            "unique": False,
                            "partial": field_def.index_partial,
                            "where": "is_available = 1"
                            if field_def.index_partial
                            else None,
                        }
                    )

        if schema.indexes:
            for idx_def in schema.indexes:
                index_name = idx_def.get(
                    "name",
                    f"idx_{schema.name}_{'_'.join(idx_def.get('columns', []))}",
                )
                if index_name not in existing_index_names:
                    if schema.name not in diff.new_indexes:
                        diff.new_indexes[schema.name] = []
                    diff.new_indexes[schema.name].append(idx_def)

    def _compute_constraint_diff(
        self,
        schema: SchemaConfig,
        existing_table: TableMetadata,
        diff: SchemaDiff,
    ) -> None:
        """Compute differences in constraints between schema and existing table."""
        existing_unique = set()
        for col in existing_table.columns:
            if col.get("primary_key"):
                existing_unique.add(col["name"])

        for field_def in schema.fields:
            if field_def.unique:
                if field_def.name not in existing_unique:
                    if schema.name not in diff.new_constraints:
                        diff.new_constraints[schema.name] = []
                    diff.new_constraints[schema.name].append(
                        {"type": "unique", "columns": [field_def.name]}
                    )

    def _table_has_data(self, table_name: str) -> bool:
        """Check if a table has any data."""
        if self._cursor is None:
            return False
        try:
            self._cursor.execute(f"SELECT 1 FROM {table_name} LIMIT 1")
            return self._cursor.fetchone() is not None
        except Exception:
            return False


def load_schemas_from_directory(
    schema_dir: Path, cursor: sqlite3.Cursor
) -> tuple[SchemaDiffEngine, SchemaDiff, list[SchemaConfig]]:
    """Load schemas from directory and compute diff against database.

    Args:
        schema_dir: Path to directory containing schema YAML files
        cursor: SQLite cursor for reading existing schema

    Returns:
        Tuple of (SchemaDiffEngine, SchemaDiff, schemas_list)
    """
    engine = SchemaDiffEngine(cursor=cursor)
    engine.load_existing_schema(cursor)
    schemas = engine.load_schemas_from_files(schema_dir)
    diff = engine.compute_diff(schemas)
    return engine, diff, schemas
