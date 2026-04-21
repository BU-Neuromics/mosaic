"""Schema diff engine for detecting additive changes between a LinkML schema and a database."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any, Optional

from linkml_runtime.linkml_model.meta import SlotDefinition

from hippo.linkml_bridge import (
    HIPPO_INDEX,
    HIPPO_INDEX_PARTIAL,
    HIPPO_UNIQUE,
    SchemaRegistry,
    annotation_value,
)


@dataclass
class TableMetadata:
    """Metadata for an existing database table."""

    name: str
    columns: list[dict[str, Any]] = field(default_factory=list)
    indexes: list[dict[str, Any]] = field(default_factory=list)
    foreign_keys: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SchemaDiff:
    """Difference between the desired LinkML schema and the live database."""

    new_tables: list[str] = field(default_factory=list)
    new_columns: dict[str, list[SlotDefinition]] = field(default_factory=dict)
    new_indexes: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    new_constraints: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class SchemaDiffEngine:
    """Compute diffs between a ``SchemaRegistry`` and a SQLite database."""

    def __init__(self, cursor: Optional[sqlite3.Cursor] = None):
        self._existing_tables: dict[str, TableMetadata] = {}
        self._cursor = cursor

    def set_cursor(self, cursor: sqlite3.Cursor) -> None:
        self._cursor = cursor

    def load_existing_schema(self, cursor: sqlite3.Cursor) -> None:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'fts_%'"
        )
        names = [row[0] for row in cursor.fetchall()]
        for table_name in names:
            meta = TableMetadata(name=table_name)
            cursor.execute(f"PRAGMA table_info('{table_name}')")
            meta.columns = [
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
            meta.indexes = [
                {"name": row[1], "unique": bool(row[2]), "origin": row[3]}
                for row in cursor.fetchall()
            ]
            cursor.execute(f"PRAGMA foreign_key_list('{table_name}')")
            meta.foreign_keys = [
                {"table": row[2], "from": row[3], "to": row[4], "on_delete": row[5]}
                for row in cursor.fetchall()
            ]
            self._existing_tables[table_name] = meta

    def compute_diff(self, registry: SchemaRegistry) -> SchemaDiff:
        diff = SchemaDiff()
        sv = registry.schema_view
        for class_name in registry.class_names():
            cls = sv.get_class(class_name)
            if cls is None or cls.abstract:
                continue
            if class_name not in self._existing_tables:
                diff.new_tables.append(class_name)
                continue
            existing = self._existing_tables[class_name]
            self._diff_columns(registry, class_name, existing, diff)
            self._diff_indexes(registry, class_name, existing, diff)
            self._diff_constraints(registry, class_name, existing, diff)
        return diff

    def _diff_columns(
        self,
        registry: SchemaRegistry,
        class_name: str,
        existing: TableMetadata,
        diff: SchemaDiff,
    ) -> None:
        existing_cols = {col["name"] for col in existing.columns}
        for slot in registry.induced_slots(class_name):
            if slot.name in existing_cols:
                continue
            diff.new_columns.setdefault(class_name, []).append(slot)
            if slot.required:
                if slot.ifabsent is None:
                    if self._table_has_data(class_name):
                        diff.warnings.append(
                            f"Adding NOT NULL column '{slot.name}' to table '{class_name}' "
                            f"with existing data but no default value defined"
                        )

    def _diff_indexes(
        self,
        registry: SchemaRegistry,
        class_name: str,
        existing: TableMetadata,
        diff: SchemaDiff,
    ) -> None:
        existing_idx_names = {idx["name"] for idx in existing.indexes}
        for slot in registry.induced_slots(class_name):
            if not annotation_value(slot, HIPPO_INDEX):
                continue
            name = f"idx_{class_name}_{slot.name}"
            if name in existing_idx_names:
                continue
            partial = bool(annotation_value(slot, HIPPO_INDEX_PARTIAL))
            diff.new_indexes.setdefault(class_name, []).append(
                {
                    "name": name,
                    "columns": [slot.name],
                    "unique": False,
                    "partial": partial,
                    "where": "is_available = 1" if partial else None,
                }
            )

    def _diff_constraints(
        self,
        registry: SchemaRegistry,
        class_name: str,
        existing: TableMetadata,
        diff: SchemaDiff,
    ) -> None:
        existing_unique = {
            col["name"] for col in existing.columns if col.get("primary_key")
        }
        for slot in registry.induced_slots(class_name):
            if annotation_value(slot, HIPPO_UNIQUE) and slot.name not in existing_unique:
                diff.new_constraints.setdefault(class_name, []).append(
                    {"type": "unique", "columns": [slot.name]}
                )

    def _table_has_data(self, table_name: str) -> bool:
        if self._cursor is None:
            return False
        try:
            self._cursor.execute(f"SELECT 1 FROM {table_name} LIMIT 1")
            return self._cursor.fetchone() is not None
        except Exception:
            return False


def diff_registry_against_database(
    registry: SchemaRegistry, cursor: sqlite3.Cursor
) -> tuple[SchemaDiffEngine, SchemaDiff]:
    """Load existing DB state and diff against the given registry."""
    engine = SchemaDiffEngine(cursor=cursor)
    engine.load_existing_schema(cursor)
    return engine, engine.compute_diff(registry)
