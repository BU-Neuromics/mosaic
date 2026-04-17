"""SQLite summary views generated from a LinkML-backed SchemaRegistry."""

from __future__ import annotations

import sqlite3
from typing import Iterable, Optional

from hippo.linkml_bridge import SchemaRegistry


NUMERIC_RANGES = {"integer", "float", "double", "decimal"}


class SummaryViewGenerator:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def generate_summary_views(
        self, registry: SchemaRegistry, class_names: Optional[Iterable[str]] = None
    ) -> list[str]:
        names = list(class_names) if class_names is not None else registry.class_names()
        sv = registry.schema_view
        ddl: list[str] = []
        for class_name in names:
            cls = sv.get_class(class_name)
            if cls is None or cls.abstract:
                continue
            ddl.append(self._count_view_ddl(class_name))
            agg = self._aggregate_view_ddl(registry, class_name)
            if agg:
                ddl.append(agg)
        return ddl

    def generate_all_summary_views(self, registry: SchemaRegistry) -> list[str]:
        return self.generate_summary_views(registry)

    def _count_view_ddl(self, class_name: str) -> str:
        view = f"summary_{class_name}_count"
        return (
            f'\nCREATE VIEW IF NOT EXISTS "{view}" AS\n'
            f"SELECT COUNT(*) as count\n"
            f'FROM "{class_name}"\n'
        )

    def _aggregate_view_ddl(
        self, registry: SchemaRegistry, class_name: str
    ) -> Optional[str]:
        numeric_slots = [
            slot.name
            for slot in registry.induced_slots(class_name)
            if slot.range in NUMERIC_RANGES
        ]
        if not numeric_slots:
            return None
        view = f"summary_{class_name}_aggregate"
        cols = []
        for name in numeric_slots:
            cols.append(f"COUNT({name}) as {name}_count")
            cols.append(f"SUM({name}) as {name}_sum")
            cols.append(f"AVG({name}) as {name}_avg")
        return (
            f'\nCREATE VIEW IF NOT EXISTS "{view}" AS\nSELECT\n    '
            + ",\n    ".join(cols)
            + f'\nFROM "{class_name}"\n'
        )

    def create_views_in_migration(self, registry: SchemaRegistry) -> None:
        with self.connection:
            cursor = self.connection.cursor()
            for ddl in self.generate_summary_views(registry):
                try:
                    cursor.execute(ddl)
                except Exception as e:
                    print(f"Error creating view: {e}")
