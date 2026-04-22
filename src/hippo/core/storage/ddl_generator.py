"""DDL generation from a LinkML-backed SchemaRegistry.

Walks the classes exposed by a ``SchemaRegistry``, maps LinkML built-in types
to SQLite column types, and emits ``CREATE TABLE`` / ``CREATE INDEX`` statements
with Hippo's system columns (``is_available``, ``superseded_by``) and
partial-index semantics. LinkML's own SQL generator is not used directly
because we need Hippo-specific naming conventions and system columns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from hippo.core.storage.fts import FTSFieldMetadata, FTSTableMetadata
from hippo.linkml_bridge import (
    HIPPO_INDEX,
    HIPPO_INDEX_PARTIAL,
    HIPPO_UNIQUE,
    SchemaRegistry,
    annotation_value,
    slot_default,
)


@dataclass
class ColumnDefinition:
    name: str
    column_type: str
    not_null: bool = False
    default: Any = None
    primary_key: bool = False


@dataclass
class ForeignKeyDefinition:
    columns: list[str]
    references_table: str
    references_columns: list[str]
    on_delete: Optional[str] = None


@dataclass
class IndexDefinition:
    name: str
    columns: list[str]
    unique: bool = False
    partial_where: Optional[str] = None


@dataclass
class TableDefinition:
    name: str
    columns: list[ColumnDefinition] = field(default_factory=list)
    foreign_keys: list[ForeignKeyDefinition] = field(default_factory=list)
    unique_constraints: list[list[str]] = field(default_factory=list)
    indexes: list[IndexDefinition] = field(default_factory=list)


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
        self._tables: dict[str, TableDefinition] = {}

    def generate(self, registry: SchemaRegistry) -> list[str]:
        self._tables = {}
        sv = registry.schema_view

        for class_name in registry.class_names():
            cls = sv.get_class(class_name)
            if cls is None or cls.abstract:
                continue
            self._build_table(registry, class_name)

        ordered = self._topological_sort()
        statements: list[str] = []
        for name in ordered:
            table = self._tables[name]
            statements.append(self._render_create_table(table))
            for index in table.indexes:
                statements.append(self._render_create_index(name, index))
        return statements

    def _build_table(
        self, registry: SchemaRegistry, class_name: str
    ) -> TableDefinition:
        if class_name in self._tables:
            return self._tables[class_name]

        sv = registry.schema_view
        cls = sv.get_class(class_name)
        table = TableDefinition(name=class_name)

        id_slot = registry.identifier_slot(class_name)
        id_name = id_slot.name if id_slot is not None else "id"
        table.columns.append(
            ColumnDefinition(
                name=id_name, column_type="TEXT", not_null=True, primary_key=True
            )
        )

        known_classes = set(registry.class_names())
        for slot in registry.induced_slots(class_name):
            if slot.name == id_name:
                continue
            col_type = self._map_slot_type(slot, known_classes)
            default = slot_default(slot)
            column = ColumnDefinition(
                name=slot.name,
                column_type=col_type,
                not_null=bool(slot.required),
                default=default,
            )
            table.columns.append(column)

            if annotation_value(slot, HIPPO_UNIQUE):
                table.unique_constraints.append([slot.name])

            if annotation_value(slot, HIPPO_INDEX):
                partial = bool(annotation_value(slot, HIPPO_INDEX_PARTIAL))
                table.indexes.append(
                    IndexDefinition(
                        name=f"idx_{class_name}_{slot.name}",
                        columns=[slot.name],
                        partial_where=self.IS_AVAILABLE_PREDICATE if partial else None,
                    )
                )

            if slot.range in known_classes:
                table.foreign_keys.append(
                    ForeignKeyDefinition(
                        columns=[slot.name],
                        references_table=slot.range,
                        references_columns=["id"],
                    )
                )

        # is_available: preferred path is declared on Entity in hippo_core
        # (flows in via induced_slots above). Fallback hardcoded here for
        # schemas that don't `is_a: Entity` (e.g., ad-hoc test fixtures).
        # superseded_by stays hardcoded for now; scheduled to be redesigned in
        # the Wave 2 provenance-as-linkml-class change where supersession is
        # modeled via ProvenanceRecord.
        existing_column_names = {col.name for col in table.columns}
        if "is_available" not in existing_column_names:
            table.columns.append(
                ColumnDefinition(
                    name="is_available",
                    column_type="INTEGER",
                    not_null=True,
                    default=1,
                )
            )
        table.columns.append(
            ColumnDefinition(
                name="superseded_by", column_type="TEXT", not_null=False, default=None
            )
        )

        for uk in (cls.unique_keys or {}).values():
            slots = list(uk.unique_key_slots or [])
            if slots:
                table.unique_constraints.append(slots)

        for parent_name in cls.is_a and [cls.is_a] or []:
            parent_cls = sv.get_class(parent_name)
            if parent_cls is not None and not parent_cls.abstract:
                self._build_table(registry, parent_name)
                table.foreign_keys.append(
                    ForeignKeyDefinition(
                        columns=[id_name],
                        references_table=parent_name,
                        references_columns=[id_name],
                        on_delete="CASCADE",
                    )
                )

        self._tables[class_name] = table
        return table

    def _map_slot_type(self, slot: Any, known_classes: set[str]) -> str:
        rng = slot.range
        if rng in known_classes:
            return "TEXT"
        if rng is None:
            return "TEXT"
        return self.TYPE_MAPPING.get(rng, "TEXT")

    def _topological_sort(self) -> list[str]:
        visited: set[str] = set()
        ordered: list[str] = []

        def visit(name: str) -> None:
            if name in visited:
                return
            visited.add(name)
            table = self._tables.get(name)
            if table is not None:
                for fk in table.foreign_keys:
                    if fk.references_table in self._tables:
                        visit(fk.references_table)
            ordered.append(name)

        for name in self._tables:
            visit(name)
        return ordered

    def _render_create_table(self, table: TableDefinition) -> str:
        pieces: list[str] = []
        pk_cols = [c.name for c in table.columns if c.primary_key]

        for col in table.columns:
            col_sql = f'"{col.name}" {col.column_type}'
            if col.primary_key and len(pk_cols) == 1:
                col_sql += " PRIMARY KEY"
            if col.not_null and not col.primary_key:
                col_sql += " NOT NULL"
            if col.default is not None:
                col_sql += f" DEFAULT {self._format_default(col.default)}"
            pieces.append(col_sql)

        for fk in table.foreign_keys:
            cols = ", ".join(f'"{c}"' for c in fk.columns)
            refs = ", ".join(f'"{c}"' for c in fk.references_columns)
            fk_sql = f'FOREIGN KEY ({cols}) REFERENCES "{fk.references_table}"({refs})'
            if fk.on_delete:
                fk_sql += f" ON DELETE {fk.on_delete}"
            pieces.append(fk_sql)

        if len(pk_cols) > 1:
            pk_sql = ", ".join(f'"{c}"' for c in pk_cols)
            pieces.append(f"PRIMARY KEY ({pk_sql})")

        for unique_cols in table.unique_constraints:
            cols = ", ".join(f'"{c}"' for c in unique_cols)
            pieces.append(f"UNIQUE ({cols})")

        return f'CREATE TABLE "{table.name}" (\n    ' + ",\n    ".join(pieces) + "\n);"

    def _render_create_index(self, table_name: str, index: IndexDefinition) -> str:
        cols = ", ".join(f'"{c}"' for c in index.columns)
        if index.partial_where:
            return (
                f'CREATE INDEX "{index.name}" ON "{table_name}" ({cols}) '
                f"WHERE {index.partial_where};"
            )
        unique = "UNIQUE " if index.unique else ""
        return f'CREATE {unique}INDEX "{index.name}" ON "{table_name}" ({cols});'

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
