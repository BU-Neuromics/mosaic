"""FTS5 (Full-Text Search) related models and utilities."""

import math
import sqlite3
from dataclasses import dataclass
from typing import Any, Optional


def normalize_bm25_score(
    bm25_score: float, k: float = 0.5, threshold: float = 0.0
) -> float:
    """Normalize BM25 score to [0.0, 1.0] range using exponential decay.

    Args:
        bm25_score: The raw BM25 score from FTS5 (negative values).
        k: Controls the steepness of the curve (default 0.5).
        threshold: BM25 threshold for normalization (default 0.0).

    Returns:
        Normalized score in range [0.0, 1.0].
    """
    normalized = 1.0 / (1.0 + math.exp(-k * (bm25_score - threshold)))
    return max(0.0, min(1.0, normalized))


@dataclass
class FTSFieldMetadata:
    """Metadata for an FTS-indexed field."""

    field_name: str
    field_type: str
    search_type: str
    source_entity_type: str


@dataclass
class FTSTableMetadata:
    """Metadata for an FTS5 virtual table."""

    table_name: str
    source_entity_type: str
    fts_version: str
    content_table: str
    content_rowid: str
    fields: list[FTSFieldMetadata]

    @property
    def is_external_content(self) -> bool:
        """Whether this FTS table uses external content mode."""
        return self.content_table is not None

    def get_fts_columns(self) -> list[str]:
        """Get the column names for the FTS table."""
        return [f.field_name for f in self.fields]

    @classmethod
    def generate_table_name(cls, entity_type: str, field_name: str) -> str:
        """Generate the FTS table name for a field."""
        return f"fts_{entity_type.lower()}_{field_name.lower()}"

    @classmethod
    def from_field(
        cls,
        field,
        entity_type: str,
        content_table: str = "entities",
    ) -> "FTSTableMetadata":
        """Create FTS table metadata from a field definition."""
        table_name = cls.generate_table_name(entity_type, field.name)
        fts_version = field.search if field.search else "fts5"

        field_metadata = FTSFieldMetadata(
            field_name=field.name,
            field_type=field.type,
            search_type=fts_version,
            source_entity_type=entity_type,
        )

        return cls(
            table_name=table_name,
            source_entity_type=entity_type,
            fts_version=fts_version,
            content_table=content_table,
            content_rowid="rowid",
            fields=[field_metadata],
        )

    def create(self, conn: sqlite3.Connection) -> None:
        """Create the FTS table in the database."""
        cursor = conn.cursor()
        columns = self.get_fts_columns()
        fts_columns = generate_fts_column_definitions(columns)
        sql = generate_fts_create_sql(
            table_name=self.table_name,
            columns=fts_columns,
            content_table=self.content_table,
            content_rowid=self.content_rowid,
        )
        cursor.execute(sql)


def generate_fts_create_sql(
    table_name: str,
    columns: list[str],
    content_table: Optional[str] = None,
    content_rowid: str = "rowid",
) -> str:
    """Generate SQL to create an FTS5 virtual table.

    Args:
        table_name: Name of the FTS table to create.
        columns: List of column names to include in the FTS index.
        content_table: Optional external content table name.
        content_rowid: The rowid column in the content table.

    Returns:
        SQL CREATE VIRTUAL TABLE statement.
    """
    if content_table:
        return f"""CREATE VIRTUAL TABLE IF NOT EXISTS {table_name} USING fts5(
            {", ".join(columns)},
            content='{content_table}',
            content_rowid='{content_rowid}'
        )"""
    else:
        return f"""CREATE VIRTUAL TABLE IF NOT EXISTS {table_name} USING fts5(
            {", ".join(columns)}
        )"""


def generate_fts_insert_sql(table_name: str, columns: list[str]) -> str:
    """Generate SQL to insert into an FTS table."""
    col_list = ", ".join(columns)
    placeholders = ", ".join(["?" for _ in columns])
    return f"INSERT INTO {table_name} ({col_list}) VALUES ({placeholders})"


def generate_fts_delete_sql(table_name: str, rowid_column: str = "rowid") -> str:
    """Generate SQL to delete from an FTS table by rowid."""
    return f"DELETE FROM {table_name} WHERE {rowid_column} = ?"


def generate_fts_update_sql(
    table_name: str, columns: list[str], rowid_column: str = "rowid"
) -> str:
    """Generate SQL to update an FTS table row."""
    set_clause = ", ".join([f"{col} = ?" for col in columns])
    return f"UPDATE {table_name} SET {set_clause} WHERE {rowid_column} = ?"


def get_fts_tables_for_entity_type(cursor, entity_type: str) -> list[str]:
    """Get list of FTS virtual table names for an entity type.

    Uses ``type='shadow'`` exclusion: FTS5 shadow tables have names like
    ``<base>_data``, ``<base>_idx``, etc.  We only return the virtual table
    itself by querying for ``type='table'`` rows that are also listed as
    virtual tables (i.e. present in ``sqlite_master`` with a ``CREATE
    VIRTUAL TABLE`` statement).
    """
    cursor.execute(
        """SELECT name FROM sqlite_master
           WHERE type='table'
             AND name LIKE ?
             AND sql LIKE 'CREATE VIRTUAL TABLE%'""",
        (f"fts_{entity_type}_%",),
    )
    return [row[0] for row in cursor.fetchall()]


def fts_table_exists(cursor, table_name: str) -> bool:
    """Check if an FTS table exists."""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def generate_fts_query(
    search_term: str,
    field_name: Optional[str] = None,
    prefix_search: bool = False,
) -> str:
    """Generate an FTS5 query string.

    Args:
        search_term: The search term.
        field_name: Optional field to search in.
        prefix_search: Whether to use prefix search (* suffix).

    Returns:
        FTS5 query string.
    """
    if field_name:
        if prefix_search:
            return f"{field_name}:{search_term}*"
        return f"{field_name}:{search_term}"
    if prefix_search:
        return f"{search_term}*"
    return search_term


def generate_fts_phrase_query(phrase: str, field_name: Optional[str] = None) -> str:
    """Generate an FTS5 phrase query.

    Args:
        phrase: The phrase to search for.
        field_name: Optional field to search in.

    Returns:
        FTS5 phrase query string.
    """
    if field_name:
        return f'"{field_name}":"{phrase}"'
    return f'"{phrase}"'


def generate_fts_boolean_query(
    terms: list[str],
    operator: str = "AND",
    field_name: Optional[str] = None,
) -> str:
    """Generate an FTS5 boolean query.

    Args:
        terms: List of search terms.
        operator: Boolean operator (AND, OR, NOT).
        field_name: Optional field to search in.

    Returns:
        FTS5 boolean query string.
    """
    prefix = f"{field_name}:" if field_name else ""
    return f" {operator} ".join([f"{prefix}{term}" for term in terms])


def map_fts_results_to_entities(
    storage,
    entity_type: str,
    fts_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Map FTS search results to entity data.

    Args:
        storage: The storage adapter.
        entity_type: The entity type.
        fts_results: List of FTS search results.

    Returns:
        List of entity data dictionaries.
    """
    entities = []
    for fts_result in fts_results:
        entity_id = fts_result.get("entity_id")
        if entity_id:
            entity = storage.read(entity_id)
            if entity and entity.entity_type == entity_type and entity.is_available:
                entities.append(
                    {
                        "id": entity.id,
                        "entity_type": entity.entity_type,
                        "data": entity.data,
                        "version": entity.version,
                        "created_at": entity.created_at,
                        "updated_at": entity.updated_at,
                        "_fts_content": fts_result.get("content"),
                    }
                )
    return entities


def generate_fts_column_definitions(
    fields: list[str],
    include_entity_id: bool = True,
) -> list[str]:
    """Generate column definitions for an FTS table.

    Args:
        fields: List of field names to include.
        include_entity_id: Whether to include entity_id column.

    Returns:
        List of column definitions for FTS table.
    """
    columns = []
    if include_entity_id:
        columns.append("entity_id")
    for field in fields:
        columns.append(f"{field}")
    return columns
