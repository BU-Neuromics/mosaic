"""DDL generation from a LinkML-backed SchemaRegistry.

Delegates base DDL generation to LinkML's ``SQLTableGenerator``, then
post-processes for Hippo-specific extras: ``superseded_by`` column,
partial indexes (``hippo_index_partial``), FTS5 virtual tables
(``hippo_search: fts5``), and append-only triggers (``hippo_append_only``).
"""

from __future__ import annotations

import re
import tempfile
import yaml
from pathlib import Path
from typing import Any

from linkml.generators.sqltablegen import SQLTableGenerator

from hippo.core.storage.fts import FTSFieldMetadata, FTSTableMetadata
from hippo.linkml_bridge import (
    HIPPO_APPEND_ONLY,
    HIPPO_INDEX,
    HIPPO_INDEX_PARTIAL,
    HIPPO_UNIQUE,
    SchemaRegistry,
    annotation_value,
    slot_default,
    _flatten_for_validator,
)


class DDLGenerator:
    """Generate SQLite DDL from a ``SchemaRegistry``."""

    TYPE_MAPPING = {
        "string": "TEXT",
        "integer": "INTEGER",
        "float": "REAL",
        "double": "REAL",
        "decimal": "REAL",
        "boolean": "INTEGER",
        "date": "TEXT",
        "datetime": "TEXT",
        "time": "TEXT",
        "uri": "TEXT",
        "uriorcurie": "TEXT",
        "curie": "TEXT",
        "ncname": "TEXT",
        "jsonpointer": "TEXT",
        "jsonpath": "TEXT",
        "sparqlpath": "TEXT",
    }

    IS_AVAILABLE_PREDICATE = "is_available = 1"

    def __init__(self) -> None:
        pass

    def generate(self, registry: SchemaRegistry) -> list[str]:
        """Generate SQLite DDL via LinkML SQLTableGenerator + Hippo post-processing."""
        sv = registry.schema_view

        # Step 1: Flatten schema to self-contained dict (resolves imports inline)
        flat_schema = _flatten_for_validator(sv)

        # Step 2: Write to temp file for SQLTableGenerator
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as tmp:
            yaml.safe_dump(flat_schema, tmp, sort_keys=False)
            tmp_path = tmp.name

        try:
            # Step 3: Generate base DDL with LinkML SQLTableGenerator
            gen = SQLTableGenerator(
                schema=tmp_path,
                generate_abstract_class_ddl=True,
                autogenerate_index=False,
            )
            raw_ddl = gen.generate_ddl()
        finally:
            Path(tmp_path).unlink()

        # Step 4: Parse DDL string into statements
        base_statements = self._parse_ddl_string(raw_ddl)

        # Step 5: Filter and post-process CREATE TABLE statements
        concrete_classes = {
            name for name in registry.class_names()
            if not (cls := sv.get_class(name)) or not cls.abstract
        }

        table_statements = []
        index_statements = []

        for stmt in base_statements:
            if "CREATE TABLE" in stmt:
                table_name = self._extract_table_name(stmt)
                # Filter: keep only concrete classes (drop linktables, abstract)
                if table_name not in concrete_classes:
                    continue
                # Post-process this CREATE TABLE
                stmt = self._post_process_create_table(stmt, registry, table_name)
                table_statements.append(stmt)
            elif "CREATE INDEX" in stmt or "CREATE UNIQUE INDEX" in stmt:
                # Indexes from SQLTableGenerator (we disabled autogenerate_index)
                index_statements.append(stmt)

        # Step 6: Add Hippo-specific indexes, unique constraints, triggers
        hippo_extras = self._generate_hippo_extras(registry, concrete_classes)

        # Step 7: Add FTS5 virtual tables
        fts_planner = FTSMigrationPlanner()
        fts_planner.add_registry(registry)
        fts_statements = fts_planner.generate_fts_ddl()

        return table_statements + hippo_extras + index_statements + fts_statements

    def _parse_ddl_string(self, raw_ddl: str) -> list[str]:
        """Parse semicolon-delimited DDL string into statement list.

        LinkML SQLTableGenerator emits all tables in one string with comments.
        We split on CREATE TABLE markers to isolate each table statement.
        """
        statements = []
        # Split on CREATE TABLE to get individual table blocks
        parts = raw_ddl.split("\nCREATE TABLE ")
        for i, part in enumerate(parts):
            if i == 0:
                # First part is just comments before any tables
                continue
            # Reconstruct the CREATE TABLE statement
            stmt = "CREATE TABLE " + part
            # Find the end of this statement (");")
            end_idx = stmt.find(");")
            if end_idx != -1:
                stmt = stmt[:end_idx + 2]  # Include the ");
            statements.append(stmt)
        return statements

    def _extract_table_name(self, create_table_stmt: str) -> str:
        """Extract table name from 'CREATE TABLE name (...);' or 'CREATE TABLE "name" (...);'."""
        match = re.search(r'CREATE TABLE (?:"([^"]+)"|(\w+))', create_table_stmt, re.IGNORECASE)
        if not match:
            return ""
        return match.group(1) or match.group(2)

    def _post_process_create_table(
        self, stmt: str, registry: SchemaRegistry, table_name: str
    ) -> str:
        """Post-process CREATE TABLE: fix BOOLEAN→INTEGER, inject DEFAULTs, add superseded_by."""
        sv = registry.schema_view

        # Fix BOOLEAN → INTEGER for is_available (handles both quoted and unquoted)
        stmt = re.sub(
            r'\bis_available\s+BOOLEAN\b',
            'is_available INTEGER',
            stmt,
            flags=re.IGNORECASE,
        )

        # Inject DEFAULT 1 for is_available if not present (handles both quoted and unquoted)
        if 'is_available' in stmt:
            is_avail_match = re.search(
                r'\bis_available\s+INTEGER(?:\s+NOT\s+NULL)?',
                stmt,
                re.IGNORECASE
            )
            if is_avail_match and "DEFAULT" not in is_avail_match.group():
                stmt = re.sub(
                    r'(\bis_available\s+INTEGER(?:\s+NOT\s+NULL)?)',
                    r"\1 DEFAULT 1",
                    stmt,
                    flags=re.IGNORECASE,
                )

        # Inject ifabsent DEFAULTs for other slots (SQLTableGenerator doesn't emit them)
        # Handle both quoted and unquoted column names
        for slot in registry.induced_slots(table_name):
            default = slot_default(slot)
            if default is not None and slot.name != "is_available":
                # Match "name TYPE" or "\tname TYPE" - look for the column line
                # before next comma or newline
                pattern = rf'(\b{re.escape(slot.name)}\s+\w+(?:\([^)]+\))?(?:\s+NOT\s+NULL)?)'
                match = re.search(pattern, stmt, re.IGNORECASE)
                if match and "DEFAULT" not in match.group():
                    col_def = match.group()
                    new_col_def = col_def + f" DEFAULT {self._format_default(default)}"
                    stmt = stmt.replace(col_def, new_col_def, 1)

        # Fallback: add is_available if missing (for schemas without is_a: Entity)
        if not re.search(r'\bis_available\b', stmt):
            constraint_pattern = r',\n\t((?:PRIMARY KEY|FOREIGN KEY|UNIQUE|CHECK))'
            if re.search(constraint_pattern, stmt):
                stmt = re.sub(
                    constraint_pattern,
                    r',\n\t"is_available" INTEGER NOT NULL DEFAULT 1,\n\t\1',
                    stmt,
                    count=1,
                )

        # Inject superseded_by column before table constraints (PRIMARY KEY, FOREIGN KEY, etc.)
        # In SQLite, columns must come before constraints
        if 'superseded_by' not in stmt:
            # Find first constraint line (PRIMARY KEY, FOREIGN KEY, UNIQUE, CHECK)
            # and inject superseded_by before it
            constraint_pattern = r',\n\t((?:PRIMARY KEY|FOREIGN KEY|UNIQUE|CHECK))'
            if re.search(constraint_pattern, stmt):
                stmt = re.sub(
                    constraint_pattern,
                    r',\n\t"superseded_by" TEXT,\n\t\1',
                    stmt,
                    count=1,
                )
            else:
                # No constraints, inject before closing paren
                stmt = re.sub(
                    r'\n\);$',
                    r',\n\t"superseded_by" TEXT\n);',
                    stmt,
                    flags=re.MULTILINE,
                )

        return stmt

    def _generate_hippo_extras(
        self, registry: SchemaRegistry, concrete_classes: set[str]
    ) -> list[str]:
        """Generate Hippo-specific indexes, unique constraints, triggers."""
        sv = registry.schema_view
        statements = []

        for class_name in concrete_classes:
            cls = sv.get_class(class_name)
            if cls is None:
                continue

            # hippo_index / hippo_index_partial annotations
            for slot in registry.induced_slots(class_name):
                if annotation_value(slot, HIPPO_INDEX):
                    partial = bool(annotation_value(slot, HIPPO_INDEX_PARTIAL))
                    idx_name = f"idx_{class_name}_{slot.name}"
                    idx_sql = f'CREATE INDEX "{idx_name}" ON "{class_name}" ("{slot.name}")'
                    if partial:
                        idx_sql += f" WHERE {self.IS_AVAILABLE_PREDICATE}"
                    idx_sql += ";"
                    statements.append(idx_sql)

                # hippo_unique: emit CREATE UNIQUE INDEX
                if annotation_value(slot, HIPPO_UNIQUE):
                    idx_name = f"idx_{class_name}_{slot.name}_unique"
                    statements.append(
                        f'CREATE UNIQUE INDEX "{idx_name}" ON "{class_name}" ("{slot.name}");'
                    )

            # hippo_append_only: emit trigger rejecting UPDATE/DELETE
            if annotation_value(cls, HIPPO_APPEND_ONLY):
                statements.extend(self._generate_append_only_triggers(class_name))

        return statements

    def _generate_append_only_triggers(self, table_name: str) -> list[str]:
        """Generate triggers that reject UPDATE and DELETE on append-only tables."""
        return [
            f"""CREATE TRIGGER "prevent_update_{table_name}"
BEFORE UPDATE ON "{table_name}"
BEGIN
    SELECT RAISE(ABORT, 'UPDATE not allowed on append-only table {table_name}');
END;""",
            f"""CREATE TRIGGER "prevent_delete_{table_name}"
BEFORE DELETE ON "{table_name}"
BEGIN
    SELECT RAISE(ABORT, 'DELETE not allowed on append-only table {table_name}');
END;""",
        ]

    @staticmethod
    def _format_default(value: Any) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, (int, float)):
            return str(value)
        return f"'{value}'"


class FTSMigrationPlanner:
    """Plans FTS5 virtual tables from slot ``hippo_search`` annotations."""

    def __init__(self) -> None:
        self._fts_tables: dict[str, list[FTSTableMetadata]] = {}

    def add_class(self, registry: SchemaRegistry, class_name: str) -> None:
        slots = registry.searchable_slots(class_name)
        if not slots:
            return
        tables = []
        for slot, mode in slots:
            tables.append(
                FTSTableMetadata(
                    table_name=FTSTableMetadata.generate_table_name(
                        class_name, slot.name
                    ),
                    source_entity_type=class_name,
                    fts_version=mode,
                    content_table="entities",
                    content_rowid="rowid",
                    fields=[
                        FTSFieldMetadata(
                            field_name=slot.name,
                            field_type=slot.range or "string",
                            search_type=mode,
                            source_entity_type=class_name,
                        )
                    ],
                )
            )
        self._fts_tables[class_name] = tables

    def add_registry(self, registry: SchemaRegistry) -> None:
        sv = registry.schema_view
        for class_name in registry.class_names():
            cls = sv.get_class(class_name)
            if cls is None or cls.abstract:
                continue
            self.add_class(registry, class_name)

    def get_fts_tables_for_entity_type(
        self, entity_type: str
    ) -> list[FTSTableMetadata]:
        return self._fts_tables.get(entity_type, [])

    def get_all_fts_tables(self) -> dict[str, list[FTSTableMetadata]]:
        return self._fts_tables

    def generate_fts_ddl(self) -> list[str]:
        from hippo.core.storage.fts import generate_fts_create_sql

        statements: list[str] = []
        for tables in self._fts_tables.values():
            for meta in tables:
                statements.append(
                    generate_fts_create_sql(
                        table_name=meta.table_name,
                        columns=["entity_id"] + meta.get_fts_columns(),
                        content_table=meta.content_table,
                        content_rowid=meta.content_rowid,
                    )
                )
        return statements
