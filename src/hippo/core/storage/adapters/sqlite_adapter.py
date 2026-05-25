"""SQLite storage adapter with WAL mode support.

The SQLite adapter provides:
- WAL mode for improved concurrency
- Automatic trigger creation for ProvenanceRecord immutability
- Thread-safe connection management

## ProvenanceRecord Immutability Triggers

Enforces ``hippo_append_only: true`` on the ``ProvenanceRecord`` table
(sec9 §9.6 / Decision 9.6.C) at the SQL level:

- ``prevent_provenance_update``: rejects any UPDATE on ProvenanceRecord
- ``prevent_provenance_delete``: rejects any DELETE on ProvenanceRecord

Triggers use ``CREATE TRIGGER IF NOT EXISTS`` for idempotent initialization.
"""

import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Generator, Iterator, List, Optional

if TYPE_CHECKING:
    from hippo.linkml_bridge import SchemaRegistry

from hippo.core.storage import EntityStore, Query, ScoredMatch
from hippo.core.storage.adapters import sqlite_triggers
from hippo.core.storage.fts import (
    FTSTableMetadata,
    fts_table_exists,
    generate_fts_column_definitions,
    generate_fts_create_sql,
    generate_fts_delete_sql,
    generate_fts_insert_sql,
    generate_fts_update_sql,
    get_fts_tables_for_entity_type,
    normalize_bm25_score,
)
from hippo.core.types import ProvenanceRecord as ProvenanceRecordType, TemporalRecord
from hippo.core.exceptions import SearchCapabilityError


class SQLiteEntity:
    """Entity stored in SQLite."""

    def __init__(
        self,
        id: str,
        entity_type: str,
        is_available: bool,
        version: int,
        data: dict[str, Any],
        superseded_by: Optional[str] = None,
    ):
        self.id = id
        self.entity_type = entity_type
        self.is_available = is_available
        self.version = version
        self.data = data
        self.superseded_by = superseded_by


# Legacy operation-string → Operation enum mapping (Decision 9.6.B).
# Resolved per-site via reading the surrounding code at write time;
# preserved here as a compatibility shim so callers not yet migrated to
# pass Operation enum values continue to work during the transition.
_LEGACY_OPERATION_MAP: dict[str, str] = {
    "CREATE": "create",
    "UPDATE": "update",
    "EntityUpdated": "update",
    "REPLACED": "update",
    "EntitySuperseded": "supersede",
    "SUPERSEDE": "supersede",
    "AvailabilityChanged": "availability_change",
    "AVAILABILITY_CHANGE": "availability_change",
    "SOFT_DELETE": "availability_change",
    "RELATE": "relationship_add",
    "UNRELATE": "relationship_remove",
}


def _normalize_operation(op: Any) -> str:
    """Accept an Operation enum value or legacy string; return the enum value.

    Used by ``ProvenanceStore.record()`` and its Postgres sibling to
    absorb legacy operation strings (``"CREATE"``, ``"SOFT_DELETE"``, etc.)
    during the migration to sec9 §9.6's ``Operation`` enum. See
    Decision 9.6.B for the per-site mapping rationale.
    """
    if hasattr(op, "value"):
        return op.value
    s = str(op)
    return _LEGACY_OPERATION_MAP.get(s, s)


class ProvenanceStore:
    """Store for ``ProvenanceRecord`` rows (sec9 §9.6).

    Writes the table generated from the ``hippo_core.ProvenanceRecord``
    LinkML declaration; the DDL is emitted by the shared DDL generator.
    The adapter's SQL triggers enforce append-only semantics at the DB
    level (Decision 9.6.C).
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
        schema_version: Optional[str] = None,
    ):
        self._conn = connection
        self._schema_version = schema_version or ""

    def record(
        self,
        entity_id: Optional[str],
        entity_type: Optional[str],
        # Preferred (sec9 §9.6) parameters
        operation: Any = None,
        actor_id: Optional[str] = None,
        patch: Optional[dict[str, Any]] = None,
        context: Optional[dict[str, Any]] = None,
        derived_from_id: Optional[str] = None,
        process_id: Optional[str] = None,
        schema_version: Optional[str] = None,
        # Legacy parameters — accepted during the transition and mapped
        # to the sec9 shape (Decision 9.6.B).
        operation_type: Any = None,
        user_context: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
        # Legacy fields that no longer exist in sec9 — accepted and
        # discarded so old callers don't raise TypeError.
        operation_id: Optional[str] = None,  # noqa: ARG002
        previous_state_hash: Optional[str] = None,  # noqa: ARG002
        state_snapshot: Optional[dict[str, Any]] = None,  # noqa: ARG002
    ) -> ProvenanceRecordType:
        """Record a provenance event. Accepts either sec9 kwargs or legacy kwargs."""
        import uuid
        from hippo.core.types import ProvenanceRecord as _ProvRec

        op_source = operation if operation is not None else operation_type
        if op_source is None:
            raise ValueError("operation (or legacy operation_type) is required")
        op_value = _normalize_operation(op_source)

        # actor_id resolution order (Decision 9.6.G):
        # 1. explicit kwarg passed by the caller
        # 2. legacy user_context shim (Decision 9.6.B)
        # 3. ContextVar set by middleware / with_actor() (sec9 §9.6.G)
        # 4. "unknown" sentinel — satisfies NOT NULL; signals unmigrated path
        effective_actor = actor_id if actor_id is not None else user_context
        if effective_actor is None:
            from hippo.core.context import get_current_actor
            effective_actor = get_current_actor()
        if effective_actor is None:
            effective_actor = "unknown"
        effective_patch = patch if patch is not None else payload

        now = datetime.now(timezone.utc)
        record_id = str(uuid.uuid4())
        sv = schema_version if schema_version is not None else self._schema_version

        cursor = self._conn.cursor()
        cursor.execute(
            """INSERT INTO "ProvenanceRecord"
               (id, entity_id, entity_type, operation, actor_id, timestamp,
                schema_version, derived_from_id, process_id, patch, context,
                is_available)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                record_id,
                entity_id,
                entity_type,
                op_value,
                effective_actor,
                now.isoformat(),
                sv,
                derived_from_id,
                process_id,
                json.dumps(effective_patch) if effective_patch is not None else None,
                json.dumps(context) if context is not None else None,
            ),
        )

        return _ProvRec(
            id=record_id,
            entity_id=entity_id,
            entity_type=entity_type,
            operation=op_value,
            actor_id=effective_actor,
            timestamp=now,
            schema_version=sv,
            derived_from_id=derived_from_id,
            process_id=process_id,
            patch=effective_patch,
            context=context,
        )

    def find_by_entity(
        self,
        entity_id: str,
        operation: Any = None,
        operation_type: Any = None,  # legacy alias
    ) -> Iterator[ProvenanceRecordType]:
        """Find provenance records for an entity."""
        from hippo.core.types import ProvenanceRecord as _ProvRec

        op_filter = operation if operation is not None else operation_type
        cursor = self._conn.cursor()
        sql = 'SELECT * FROM "ProvenanceRecord" WHERE entity_id = ?'
        params: list[Any] = [entity_id]

        if op_filter is not None:
            sql += " AND operation = ?"
            params.append(_normalize_operation(op_filter))

        sql += " ORDER BY timestamp DESC"

        cursor.execute(sql, params)
        for row in cursor.fetchall():
            yield _ProvRec(
                id=row["id"],
                entity_id=row["entity_id"],
                entity_type=row["entity_type"],
                operation=row["operation"],
                actor_id=row["actor_id"] or "",
                timestamp=datetime.fromisoformat(row["timestamp"]),
                schema_version=row["schema_version"] or "",
                derived_from_id=row["derived_from_id"],
                process_id=row["process_id"],
                patch=json.loads(row["patch"]) if row["patch"] else None,
                context=json.loads(row["context"]) if row["context"] else None,
            )

    def get_history(self, entity_id: str) -> list[dict[str, Any]]:
        """Get the complete change history for an entity (oldest first).

        Returns dicts shaped for legacy callers: legacy keys
        (``operation_type``, ``user_id``, ``state_snapshot``) are preserved
        by mapping onto the corresponding sec9 fields — ``state_snapshot``
        draws from ``patch``, ``user_id`` from ``actor_id``. ``previous_state_hash``
        is no longer tracked (sec9 §9.6) and is returned as ``None``.
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """SELECT id, entity_id, entity_type, operation, timestamp,
                      actor_id, patch
               FROM "ProvenanceRecord"
               WHERE entity_id = ?
               ORDER BY timestamp ASC""",
            (entity_id,),
        )

        results = []
        for row in cursor.fetchall():
            patch = json.loads(row["patch"]) if row["patch"] else None
            results.append(
                {
                    "operation_id": row["id"],
                    "entity_id": row["entity_id"],
                    "entity_type": row["entity_type"],
                    "operation_type": row["operation"],
                    "timestamp": row["timestamp"],
                    "user_id": row["actor_id"],
                    "previous_state_hash": None,
                    "state_snapshot": patch,
                }
            )
        return results

    def get_state_at(self, entity_id: str, timestamp: str) -> Optional[dict[str, Any]]:
        """Get the entity state at a specific point in time."""
        cursor = self._conn.cursor()
        cursor.execute(
            """SELECT patch, timestamp, operation
               FROM "ProvenanceRecord"
               WHERE entity_id = ? AND timestamp <= ?
               ORDER BY timestamp DESC
               LIMIT 1""",
            (entity_id, timestamp),
        )

        row = cursor.fetchone()
        if row is None:
            return None

        # availability_change with status=deleted supersedes the old
        # SOFT_DELETE operation (Decision 9.6.B) — treat as unavailable.
        if row["operation"] == "availability_change":
            patch_obj = json.loads(row["patch"]) if row["patch"] else {}
            if (
                patch_obj.get("status") == "deleted"
                or patch_obj.get("is_available") is False
            ):
                return None

        return {
            "entity_id": entity_id,
            "state": json.loads(row["patch"]) if row["patch"] else None,
            "timestamp": row["timestamp"],
        }

    def get_entity_creation_time(self, entity_id: str) -> Optional[str]:
        """Get the creation timestamp of an entity."""
        cursor = self._conn.cursor()
        cursor.execute(
            """SELECT timestamp FROM "ProvenanceRecord"
               WHERE entity_id = ? AND operation = 'create'
               ORDER BY timestamp ASC
               LIMIT 1""",
            (entity_id,),
        )
        row = cursor.fetchone()
        return row["timestamp"] if row else None

    def get_provenance_timestamps(
        self, entity_id: str
    ) -> Optional[dict[str, Optional[str]]]:
        """Legacy single-entity timestamp derivation. Kept for backward compat;
        new callers should use ``get_temporal([entity_id])`` instead.
        """
        out = self.get_temporal([entity_id])
        if entity_id not in out:
            return None
        rec = out[entity_id]
        return {
            "created_at": rec.created_at,
            "updated_at": rec.updated_at,
        }

    def get_temporal(
        self, entity_ids: list[str]
    ) -> "dict[str, TemporalRecord]":
        """Batch-derive sec9 §9.7 temporal fields for the given entities.

        Returns a dict mapping ``entity_id`` → ``TemporalRecord``. An
        ``entity_id`` that has no ``ProvenanceRecord`` rows is absent from
        the returned dict (caller decides whether to raise
        ``ProvenanceIntegrityError``). Uses a single SQL round-trip via
        aggregation + a correlated subquery for the latest record's
        ``schema_version`` and ``actor_id``.

        SQL strategy:
        - ``MIN(timestamp) WHERE operation='create'`` → created_at.
        - ``MAX(timestamp)`` excluding availability-deletion events →
          updated_at. Availability-deletion patches carry
          ``status='deleted'`` or ``is_available=0``.
        - ``actor_id`` of the earliest ``create`` → created_by.
        - For ``updated_by`` and ``schema_version``, read the single
          latest non-deletion record per entity via a GROUP BY subquery.
        """
        from hippo.core.types import TemporalRecord

        if not entity_ids:
            return {}

        placeholders = ",".join("?" for _ in entity_ids)
        cursor = self._conn.cursor()
        cursor.execute(
            f"""WITH target AS (
                    SELECT entity_id, operation, timestamp, actor_id,
                           schema_version, patch
                    FROM "ProvenanceRecord"
                    WHERE entity_id IN ({placeholders})
                ),
                agg AS (
                    SELECT
                        entity_id,
                        MIN(CASE WHEN operation = 'create'
                                 THEN timestamp END) AS created_at,
                        MAX(CASE
                            WHEN operation = 'availability_change'
                                 AND (json_extract(patch, '$.status') = 'deleted'
                                      OR json_extract(patch, '$.is_available') = 0)
                                THEN NULL
                            ELSE timestamp
                        END) AS updated_at
                    FROM target
                    GROUP BY entity_id
                )
                SELECT
                    agg.entity_id,
                    agg.created_at,
                    agg.updated_at,
                    (SELECT actor_id FROM target t
                     WHERE t.entity_id = agg.entity_id
                       AND t.operation = 'create'
                       AND t.timestamp = agg.created_at
                     LIMIT 1) AS created_by,
                    (SELECT actor_id FROM target t
                     WHERE t.entity_id = agg.entity_id
                       AND t.timestamp = agg.updated_at
                     LIMIT 1) AS updated_by,
                    (SELECT schema_version FROM target t
                     WHERE t.entity_id = agg.entity_id
                       AND t.timestamp = agg.updated_at
                     LIMIT 1) AS schema_version
                FROM agg""",
            tuple(entity_ids),
        )

        result: dict[str, TemporalRecord] = {}
        for row in cursor.fetchall():
            eid = row["entity_id"]
            result[eid] = TemporalRecord(
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                schema_version=row["schema_version"] or None,
                created_by=row["created_by"] or None,
                updated_by=row["updated_by"] or None,
            )
        return result


class RelationshipRecord:
    """Relationship between two entities."""

    def __init__(
        self,
        id: str,
        source_id: str,
        target_id: str,
        relationship_type: str,
        metadata: Optional[dict[str, Any]],
        created_at: str,
        created_by: Optional[str],
        is_available: bool = True,
    ):
        self.id = id
        self.source_id = source_id
        self.target_id = target_id
        self.relationship_type = relationship_type
        self.metadata = metadata
        self.created_at = created_at
        self.created_by = created_by
        self.is_available = is_available


class RelationshipStore:
    """Store for relationship records in SQLite."""

    def __init__(self, connection: sqlite3.Connection):
        self._conn = connection

    def create(
        self,
        source_id: str,
        target_id: str,
        relationship_type: str,
        created_by: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> RelationshipRecord:
        """Create a new relationship."""
        import uuid

        now = datetime.now(timezone.utc).isoformat()
        rel_id = str(uuid.uuid4())

        cursor = self._conn.cursor()
        cursor.execute(
            """INSERT INTO relationships (id, source_id, target_id, relationship_type, metadata, created_at, created_by, is_available)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                rel_id,
                source_id,
                target_id,
                relationship_type,
                json.dumps(metadata) if metadata else None,
                now,
                created_by,
            ),
        )

        return RelationshipRecord(
            id=rel_id,
            source_id=source_id,
            target_id=target_id,
            relationship_type=relationship_type,
            metadata=metadata,
            created_at=now,
            created_by=created_by,
            is_available=True,
        )

    def delete(self, source_id: str, target_id: str, relationship_type: str) -> bool:
        """Soft delete a relationship."""
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.cursor()
        cursor.execute(
            """UPDATE relationships SET is_available = 0, created_at = ?
               WHERE source_id = ? AND target_id = ? AND relationship_type = ? AND is_available = 1""",
            (now, source_id, target_id, relationship_type),
        )
        return cursor.rowcount > 0

    def find_by_source(
        self, source_id: str, relationship_type: Optional[str] = None
    ) -> Iterator[RelationshipRecord]:
        """Find relationships by source entity."""
        cursor = self._conn.cursor()
        sql = "SELECT * FROM relationships WHERE source_id = ? AND is_available = 1"
        params = [source_id]

        if relationship_type:
            sql += " AND relationship_type = ?"
            params.append(relationship_type)

        cursor.execute(sql, params)
        for row in cursor.fetchall():
            yield self._row_to_relationship(row)

    def find_by_target(
        self, target_id: str, relationship_type: Optional[str] = None
    ) -> Iterator[RelationshipRecord]:
        """Find relationships by target entity."""
        cursor = self._conn.cursor()
        sql = "SELECT * FROM relationships WHERE target_id = ? AND is_available = 1"
        params = [target_id]

        if relationship_type:
            sql += " AND relationship_type = ?"
            params.append(relationship_type)

        cursor.execute(sql, params)
        for row in cursor.fetchall():
            yield self._row_to_relationship(row)

    def find(
        self,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        relationship_type: Optional[str] = None,
    ) -> Iterator[RelationshipRecord]:
        """Find relationships matching criteria."""
        cursor = self._conn.cursor()
        conditions = ["is_available = 1"]
        params = []

        if source_id:
            conditions.append("source_id = ?")
            params.append(source_id)
        if target_id:
            conditions.append("target_id = ?")
            params.append(target_id)
        if relationship_type:
            conditions.append("relationship_type = ?")
            params.append(relationship_type)

        sql = f"SELECT * FROM relationships WHERE {' AND '.join(conditions)}"
        cursor.execute(sql, params)
        for row in cursor.fetchall():
            yield self._row_to_relationship(row)

    def traverse(
        self,
        source_id: str,
        relationship_type: Optional[str] = None,
        max_depth: int = 10,
    ) -> list[dict[str, Any]]:
        """Traverse relationships using recursive CTE."""
        cursor = self._conn.cursor()

        if relationship_type:
            cte_sql = f"""
                WITH RECURSIVE traversal(id, source_id, target_id, relationship_type, depth) AS (
                    SELECT id, source_id, target_id, relationship_type, 1
                    FROM relationships
                    WHERE source_id = ? AND relationship_type = ? AND is_available = 1
                    UNION ALL
                    SELECT r.id, r.source_id, r.target_id, r.relationship_type, t.depth + 1
                    FROM relationships r
                    INNER JOIN traversal t ON r.source_id = t.target_id
                    WHERE r.is_available = 1 AND t.depth < ?
                )
                SELECT * FROM traversal
            """
            cursor.execute(cte_sql, (source_id, relationship_type, max_depth))
        else:
            cte_sql = f"""
                WITH RECURSIVE traversal(id, source_id, target_id, relationship_type, depth) AS (
                    SELECT id, source_id, target_id, relationship_type, 1
                    FROM relationships
                    WHERE source_id = ? AND is_available = 1
                    UNION ALL
                    SELECT r.id, r.source_id, r.target_id, r.relationship_type, t.depth + 1
                    FROM relationships r
                    INNER JOIN traversal t ON r.source_id = t.target_id
                    WHERE r.is_available = 1 AND t.depth < ?
                )
                SELECT * FROM traversal
            """
            cursor.execute(cte_sql, (source_id, max_depth))

        results = []
        for row in cursor.fetchall():
            results.append(
                {
                    "id": row["id"],
                    "source_id": row["source_id"],
                    "target_id": row["target_id"],
                    "relationship_type": row["relationship_type"],
                    "depth": row["depth"],
                }
            )
        return results

    def _row_to_relationship(self, row: sqlite3.Row) -> RelationshipRecord:
        """Convert a database row to a relationship."""
        return RelationshipRecord(
            id=row["id"],
            source_id=row["source_id"],
            target_id=row["target_id"],
            relationship_type=row["relationship_type"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else None,
            created_at=row["created_at"],
            created_by=row["created_by"],
            is_available=bool(row["is_available"]),
        )


class FTSStore:
    """Store for FTS5 virtual tables."""

    def __init__(self, connection: sqlite3.Connection):
        self._conn = connection

    def create_fts_table(
        self,
        table_name: str,
        columns: list[str],
        content_table: str = "",
        content_rowid: str = "rowid",
    ) -> None:
        """Create an FTS5 virtual table.

        Always includes ``entity_id`` and ``content`` columns (the Hippo
        standard FTS schema) in addition to any caller-supplied columns.
        """
        cursor = self._conn.cursor()
        # Ensure the standard Hippo FTS columns are always present.
        # Pass include_entity_id=False because we manage entity_id ourselves.
        standard = ["entity_id", "content"]
        extra = [c for c in columns if c not in standard]
        fts_columns = generate_fts_column_definitions(
            standard + extra, include_entity_id=False
        )
        sql = generate_fts_create_sql(
            table_name=table_name,
            columns=fts_columns,
            content_table=content_table if content_table else None,
            content_rowid=content_rowid,
        )
        cursor.execute(sql)

    def sync_entity_to_fts(
        self,
        table_name: str,
        entity_id: str,
        content: str,
    ) -> None:
        """Sync an entity to the FTS table (insert or update)."""
        cursor = self._conn.cursor()
        cursor.execute(
            f"SELECT rowid FROM {table_name} WHERE entity_id = ?",
            (entity_id,),
        )
        existing = cursor.fetchone()

        if existing:
            self.update_fts_entry(table_name, entity_id, content)
        else:
            self.insert_fts_entry(table_name, entity_id, content)

    def remove_entity_from_fts(
        self,
        table_name: str,
        entity_id: str,
    ) -> None:
        """Remove an entity from the FTS table."""
        self.delete_fts_entry(table_name, entity_id)

    def drop_fts_table(self, table_name: str) -> None:
        """Drop an FTS5 virtual table."""
        cursor = self._conn.cursor()
        cursor.execute(f"DROP TABLE IF EXISTS {table_name}")

    def insert_fts_entry(
        self,
        table_name: str,
        entity_id: str,
        content: str,
    ) -> None:
        """Insert an entry into an FTS table."""
        cursor = self._conn.cursor()
        columns = ["entity_id", "content"]
        sql = generate_fts_insert_sql(table_name, columns)
        cursor.execute(sql, (entity_id, content))

    def update_fts_entry(
        self,
        table_name: str,
        entity_id: str,
        content: str,
    ) -> None:
        """Update an entry in an FTS table."""
        cursor = self._conn.cursor()
        cursor.execute(
            f"UPDATE {table_name} SET content = ? WHERE entity_id = ?",
            (content, entity_id),
        )

    def delete_fts_entry(self, table_name: str, entity_id: str) -> None:
        """Delete an entry from an FTS table."""
        cursor = self._conn.cursor()
        cursor.execute(f"DELETE FROM {table_name} WHERE entity_id = ?", (entity_id,))

    def search_fts(
        self,
        table_name: str,
        query: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Search an FTS table."""
        cursor = self._conn.cursor()
        cursor.execute(
            f"SELECT entity_id, content FROM {table_name} WHERE {table_name} MATCH ? LIMIT ?",
            (query, limit),
        )
        return [
            {"entity_id": row["entity_id"], "content": row["content"]}
            for row in cursor.fetchall()
        ]

    def get_fts_tables_for_entity_type(self, entity_type: str) -> list[str]:
        """Get all FTS tables for an entity type."""
        return get_fts_tables_for_entity_type(self._conn.cursor(), entity_type)

    def fts_table_exists(self, table_name: str) -> bool:
        """Check if an FTS table exists."""
        return fts_table_exists(self._conn.cursor(), table_name)


class SQLiteAdapter(EntityStore):
    """SQLite storage adapter with WAL mode for improved concurrency."""

    def __init__(
        self,
        database_path: str | Path,
        schema_registry: "SchemaRegistry",
        wal_mode: bool = True,
        schema_version: Optional[str] = None,
    ):
        """Initialize the SQLite adapter.

        Args:
            database_path: Path to the SQLite database file.
            schema_registry: LinkML schema registry for schema introspection
                and validation. Required for LinkML-native storage operations.
            wal_mode: Whether to enable WAL journal mode.
            schema_version: Schema version string captured on each
                ``ProvenanceRecord`` write (sec9 §9.6 / §9.7). Typically
                derived from ``SchemaRegistry.schema_view.schema.version``
                by ``HippoClient``; callers constructing the adapter
                directly may supply it explicitly. Defaults to the empty
                string (legacy transition; see Decision 9.6.F).
        """
        self.database_path = Path(database_path)
        self.schema_registry = schema_registry
        self.wal_mode = wal_mode
        self._schema_version = schema_version or ""
        self._local = threading.local()
        self._provenance_store: Optional[ProvenanceStore] = None
        self._relationship_store: Optional[RelationshipStore] = None
        self._fts_store: Optional[FTSStore] = None
        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a thread-local database connection."""
        if not hasattr(self._local, "connection") or self._local.connection is None:
            conn = sqlite3.connect(
                str(self.database_path),
                timeout=30.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            self._configure_connection(conn)
            self._local.connection = conn
        return self._local.connection

    def _configure_connection(self, conn: sqlite3.Connection) -> None:
        """Configure connection with WAL mode and other settings."""
        cursor = conn.cursor()

        if self.wal_mode:
            cursor.execute("PRAGMA journal_mode=WAL")

        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")

        conn.commit()

    @contextmanager
    def _transaction(
        self,
    ) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for database transactions."""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_database(self) -> None:
        """Initialize database schema."""
        with self._transaction() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS hippo_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # ProvenanceRecord — shape stamped inline here to match what the
            # LinkML DDL generator produces from hippo_core.ProvenanceRecord
            # (verified by tests/core/test_ddl_generator.py::
            # TestHippoCoreProvenanceRecordDDL). Per Decision 9.6.D, this
            # table replaces the legacy hand-coded `provenance` table.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS "ProvenanceRecord" (
                    id TEXT PRIMARY KEY,
                    entity_id TEXT,
                    entity_type TEXT,
                    operation TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    derived_from_id TEXT,
                    process_id TEXT,
                    patch TEXT,
                    context TEXT,
                    is_available INTEGER NOT NULL DEFAULT 1,
                    superseded_by TEXT
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ProvenanceRecord_entity_id
                ON "ProvenanceRecord"(entity_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ProvenanceRecord_operation
                ON "ProvenanceRecord"(operation)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ProvenanceRecord_timestamp
                ON "ProvenanceRecord"(timestamp)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ProvenanceRecord_process_id
                ON "ProvenanceRecord"(process_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ProvenanceRecord_entity_timestamp
                ON "ProvenanceRecord"(entity_id, timestamp)
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS relationships (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relationship_type TEXT NOT NULL,
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    created_by TEXT,
                    is_available INTEGER NOT NULL DEFAULT 1
                )
            """)

            # Shadow table for cross-class UUID → class_name lookup
            # (sec9 §9.5 / PR 2.4). With per-class typed tables,
            # ``read(uuid)`` would otherwise need to scan every class
            # table or join ``ProvenanceRecord``; this O(1) lookup is
            # maintained inline by ``create()``. Idempotent backfill
            # below covers DBs created before this table existed.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS _entity_registry (
                    uuid TEXT PRIMARY KEY,
                    class_name TEXT NOT NULL
                )
            """)
            cursor.execute("""
                INSERT OR IGNORE INTO _entity_registry (uuid, class_name)
                SELECT entity_id, entity_type
                FROM "ProvenanceRecord"
                WHERE operation = 'create'
                  AND entity_id IS NOT NULL
                  AND entity_type IS NOT NULL
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_relationships_source
                ON relationships(source_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_relationships_target
                ON relationships(target_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_relationships_type
                ON relationships(relationship_type)
            """)

            # Reference-loader write log (sec2 §2.14.9 / Decision 2.14.J).
            # Substrate for ``--prune-old``: records every entity written by
            # a reference loader inside ``HippoClient.load_context()``.
            # Composite PK collapses repeat writes of the same id within a
            # ``(loader_name, version)`` window to a single row, keeping
            # ``upgrade()`` re-writes and migration backfill idempotent.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reference_write_log (
                    loader_name TEXT NOT NULL,
                    version     TEXT NOT NULL,
                    entity_id   TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    written_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (loader_name, version, entity_id)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_reference_write_log_lookup
                ON reference_write_log (loader_name, version)
            """)

            self._init_triggers(cursor)

            # Create entity_provenance_summary view before entity-level migrations.
            # This view is REQUIRED (not optional) for correct provenance-derived field
            # derivation in client.query(). Columns:
            #   entity_id       - the entity
            #   created_at      - timestamp of earliest record for the entity
            #   updated_at      - timestamp of most recent non-deletion record
            #   schema_version  - schema_version from the latest record (sec9 §9.7)
            # Post-migration (sec9 §9.6 / Decision 9.6.D) this reads from
            # the ProvenanceRecord table with the new column shape. The
            # availability-change exclusion mirrors the earlier SOFT_DELETE
            # exclusion: patch.status == 'deleted' or is_available == 0 is
            # not an update for updated_at purposes.
            cursor.execute("""
                CREATE VIEW IF NOT EXISTS entity_provenance_summary AS
                SELECT
                    entity_id,
                    entity_type,
                    MIN(timestamp) AS created_at,
                    MAX(CASE
                        WHEN operation = 'availability_change'
                             AND (json_extract(patch, '$.status') = 'deleted'
                                  OR json_extract(patch, '$.is_available') = 0)
                            THEN NULL
                        ELSE timestamp
                    END) AS updated_at,
                    (SELECT schema_version FROM "ProvenanceRecord" p2
                     WHERE p2.entity_id = p1.entity_id
                     ORDER BY timestamp DESC LIMIT 1) AS schema_version
                FROM "ProvenanceRecord" p1
                WHERE entity_id IS NOT NULL
                GROUP BY entity_id, entity_type
            """)

            self._run_migrations(cursor)

            self._init_per_class_tables(cursor)

            self._migrate_reference_entity_ids(cursor)

    def _init_per_class_tables(self, cursor: sqlite3.Cursor) -> None:
        """Emit per-class typed tables for every concrete class in the user schema.

        Generated via :class:`DDLGenerator`, which delegates to LinkML's
        ``SQLTableGenerator`` and post-processes for Hippo extras
        (``is_available`` default, ``superseded_by`` column, partial
        indexes, FTS5 tables, append-only triggers).

        ``ProvenanceRecord`` is filtered out — it is hand-coded above to
        preserve the explicit shape relied on by ``ProvenanceStore`` and
        the ``entity_provenance_summary`` view. Statements that reference
        a name already present in ``sqlite_master`` are skipped so that
        re-initialising an existing database is idempotent.
        """
        from hippo.core.storage.ddl_generator import DDLGenerator

        ddl = DDLGenerator().generate(self.schema_registry)
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','index','trigger','view')"
        )
        # SQLite compares identifiers case-insensitively for ASCII (so
        # "DNASample" and "DnaSample" refer to the same table). Track
        # existing names in lowercase to avoid duplicate-table errors
        # when a schema declares colliding class names.
        existing = {row[0].lower() for row in cursor.fetchall()}

        for stmt in ddl:
            target = self._extract_ddl_target(stmt)
            if target == "ProvenanceRecord" or target.startswith(
                ("idx_ProvenanceRecord_", "prevent_update_ProvenanceRecord",
                 "prevent_delete_ProvenanceRecord")
            ):
                continue
            key = target.lower()
            if key in existing:
                continue
            cursor.execute(stmt)
            existing.add(key)

    @staticmethod
    def _extract_ddl_target(stmt: str) -> str:
        """Return the table/index/trigger name a CREATE statement defines."""
        match = re.search(
            r'CREATE\s+(?:VIRTUAL\s+)?(?:UNIQUE\s+)?(?:TABLE|INDEX|TRIGGER|VIEW)\s+'
            r'(?:IF\s+NOT\s+EXISTS\s+)?(?:"([^"]+)"|(\w+))',
            stmt,
            re.IGNORECASE,
        )
        if not match:
            return ""
        return match.group(1) or match.group(2) or ""

    def _per_class_table_exists(self, entity_type: str) -> bool:
        """Whether a per-class typed table for ``entity_type`` is in the schema."""
        registry = self.schema_registry
        if registry is None or not entity_type:
            return False
        if not registry.has_class(entity_type):
            return False
        cls = registry.get_class(entity_type)
        if cls is None or getattr(cls, "abstract", False):
            return False
        # ProvenanceRecord is hand-coded with its own write path; the
        # adapter's CRUD never targets it as a per-class typed table.
        return entity_type != "ProvenanceRecord"

    def _per_class_columns(self, entity_type: str) -> list[str]:
        """Return the column names actually present on the per-class table.

        Falls back to ``induced_slots`` when the table doesn't exist
        yet (used during DDL generation and tests that probe the
        registry before init). Multivalued slots and other declarations
        that LinkML emits as separate junction tables do not appear
        here.
        """
        if not self._per_class_table_exists(entity_type):
            return []
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute(f'PRAGMA table_info("{entity_type}")')
                cols = [row[1] for row in cursor.fetchall()]
        except sqlite3.Error:
            cols = []
        if cols:
            return cols
        return [slot.name for slot in self.schema_registry.induced_slots(entity_type)]

    def _project_to_columns(
        self, entity_type: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Project a user-data dict onto the columns of the per-class table.

        Drops keys that do not correspond to a slot in the class. The
        legacy ``entities.data`` blob keeps the full payload, so dropping
        here is non-lossy. System slots managed separately (``id``,
        ``is_available``, ``superseded_by``) are skipped — callers
        provide explicit values for those.
        """
        managed = {"id", "is_available", "superseded_by"}
        valid = set(self._per_class_columns(entity_type)) - managed
        return {k: v for k, v in data.items() if k in valid}

    @staticmethod
    def _coerce_for_column(value: Any) -> Any:
        """Coerce a Python value to a SQLite-storable form.

        Booleans become 0/1 integers; nested containers are JSON-encoded
        so they round-trip through TEXT columns. Scalars pass through.
        """
        if value is None:
            return None
        if isinstance(value, bool):
            return 1 if value else 0
        if isinstance(value, (list, dict)):
            return json.dumps(value)
        return value

    def _init_triggers(self, cursor: sqlite3.Cursor) -> None:
        """Initialize provenance immutability triggers."""
        for trigger_sql in sqlite_triggers.get_trigger_sql_list():
            cursor.execute(trigger_sql)

    def _run_migrations(self, cursor: sqlite3.Cursor) -> None:
        """Run database migrations for schema updates.

        Post-sec9 §9.6 migration, the legacy ``provenance`` table is
        replaced by ``ProvenanceRecord`` (created in ``_init_database``).
        Legacy column-level ADD COLUMN migrations are no longer needed;
        any dev database that still contains a legacy ``provenance``
        table should be dropped and recreated (no production deployments
        per earlier user directive).
        """
        # Drop the legacy provenance table if it exists; data migration
        # from legacy to ProvenanceRecord is not supported (dev-only
        # deployments).
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='provenance'"
        )
        if cursor.fetchone() is not None:
            cursor.execute("DROP TABLE IF EXISTS provenance")

        # Drop the legacy entities and entity_external_ids tables if a
        # pre-PR-2.3 database still has them. Data migration is not
        # supported (dev-only deployments per earlier user directive);
        # all live data is in per-class typed tables and ProvenanceRecord.
        for legacy in ("entity_external_ids", "entities"):
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (legacy,),
            )
            if cursor.fetchone() is not None:
                cursor.execute(f"DROP TABLE IF EXISTS {legacy}")

    _REFERENCE_WRITE_LOG_MIGRATION_KEY = "_reference_write_log_v1_migrated"

    def _migrate_reference_entity_ids(self, cursor: sqlite3.Cursor) -> None:
        """One-time backfill from ``hippo_meta.reference_entity_ids`` JSON
        blob to the ``reference_write_log`` table (sec2 §2.14.9).

        v1 stored ``{loader_name: {version: [entity_id, ...]}}`` under the
        ``reference_entity_ids`` meta key. v2 replaces that with the write
        log. The first ``_init_database`` after this code lands performs
        the backfill, then stamps a marker key so subsequent startups skip
        entirely. The marker is required because the v1 ``_write_versions``
        path is still in tree (removed in PTS-256) and would otherwise be
        clobbered on every adapter init.

        ``entity_type`` is resolved per id by looking it up in
        ``_entity_registry`` first (created entities) and falling back to
        ``ProvenanceRecord`` (survives any future entity deletion). Rows
        whose type cannot be resolved are skipped — preferable to a hard
        failure during init, since the prune flow that consumes the log
        is opt-in.

        ``INSERT OR IGNORE`` plus the composite primary key make the row
        writes idempotent even if a previous migration crashed after
        inserting some rows but before stamping the marker.
        """
        cursor.execute(
            "SELECT 1 FROM hippo_meta WHERE key = ?",
            (self._REFERENCE_WRITE_LOG_MIGRATION_KEY,),
        )
        if cursor.fetchone() is not None:
            return

        cursor.execute(
            "SELECT value FROM hippo_meta WHERE key = 'reference_entity_ids'"
        )
        row = cursor.fetchone()
        if row is not None:
            raw = row["value"] if isinstance(row, sqlite3.Row) else row[0]
            try:
                payload = json.loads(raw)
            except (TypeError, ValueError):
                payload = None

            if isinstance(payload, dict):
                for loader_name, by_version in payload.items():
                    if not isinstance(loader_name, str) or not isinstance(
                        by_version, dict
                    ):
                        continue
                    for version, entity_ids in by_version.items():
                        if not isinstance(version, str) or not isinstance(
                            entity_ids, list
                        ):
                            continue
                        for entity_id in entity_ids:
                            if not isinstance(entity_id, str):
                                continue
                            entity_type = (
                                self._lookup_entity_type_for_migration(
                                    cursor, entity_id
                                )
                            )
                            if entity_type is None:
                                continue
                            cursor.execute(
                                "INSERT OR IGNORE INTO reference_write_log "
                                "(loader_name, version, entity_id, entity_type) "
                                "VALUES (?, ?, ?, ?)",
                                (loader_name, version, entity_id, entity_type),
                            )

            cursor.execute(
                "DELETE FROM hippo_meta WHERE key = 'reference_entity_ids'"
            )

        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "INSERT INTO hippo_meta (key, value, updated_at) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
            "                                updated_at = excluded.updated_at",
            (
                self._REFERENCE_WRITE_LOG_MIGRATION_KEY,
                json.dumps({"completed_at": now}, sort_keys=True),
                now,
            ),
        )

    @staticmethod
    def _lookup_entity_type_for_migration(
        cursor: sqlite3.Cursor, entity_id: str
    ) -> Optional[str]:
        """Best-effort entity_type lookup used by the v1→v2 backfill.

        Checks ``_entity_registry`` first; falls back to ``ProvenanceRecord``
        in case the registry was missed (older databases predating the
        registry, or future entity-row removal).
        """
        cursor.execute(
            "SELECT class_name FROM _entity_registry WHERE uuid = ?",
            (entity_id,),
        )
        row = cursor.fetchone()
        if row is not None:
            return row["class_name"] if isinstance(row, sqlite3.Row) else row[0]
        cursor.execute(
            'SELECT entity_type FROM "ProvenanceRecord" '
            "WHERE entity_id = ? AND entity_type IS NOT NULL LIMIT 1",
            (entity_id,),
        )
        row = cursor.fetchone()
        if row is not None:
            return row["entity_type"] if isinstance(row, sqlite3.Row) else row[0]
        return None

    def _get_provenance_store(self, conn: sqlite3.Connection) -> ProvenanceStore:
        """Get or create a ProvenanceStore for the given connection."""
        if self._provenance_store is None or self._provenance_store._conn is not conn:
            self._provenance_store = ProvenanceStore(
                conn, schema_version=self._schema_version
            )
        return self._provenance_store

    def _get_relationship_store(self, conn: sqlite3.Connection) -> RelationshipStore:
        """Get or create a RelationshipStore for the given connection."""
        if self._relationship_store is None or self._relationship_store._conn is not conn:
            self._relationship_store = RelationshipStore(conn)
        return self._relationship_store

    def _get_fts_store(self, conn: Optional[sqlite3.Connection] = None) -> FTSStore:
        """Get or create an FTSStore."""
        if conn is None:
            conn = self._get_connection()
        if self._fts_store is None:
            self._fts_store = FTSStore(conn)
        return self._fts_store

    def create_fts_table(
        self,
        table_name: str,
        columns: list[str],
        content_table: str = "",
    ) -> None:
        """Create an FTS5 virtual table."""
        with self._transaction() as conn:
            fts_store = self._get_fts_store(conn)
            fts_store.create_fts_table(table_name, columns, content_table)

    def search_fts(
        self,
        table_name: str,
        query: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Search an FTS table."""
        with self._transaction() as conn:
            fts_store = self._get_fts_store(conn)
            return fts_store.search_fts(table_name, query, limit)

    def get_fts_tables_for_entity_type(self, entity_type: str) -> list[str]:
        """Get all FTS tables for an entity type."""
        with self._transaction() as conn:
            fts_store = self._get_fts_store(conn)
            return fts_store.get_fts_tables_for_entity_type(entity_type)

    def search(
        self,
        query: str,
        entity_type: str,
        field_name: str,
        min_score: float = 0.0,
        limit: int = 100,
    ) -> list[ScoredMatch]:
        """Search entities using full-text search with BM25 ranking.

        Args:
            query: The search query string.
            entity_type: The type of entities to search.
            field_name: The FTS-indexed field to search in.
            min_score: Minimum score threshold (0.0-1.0).
            limit: Maximum number of results to return.

        Returns:
            List of ScoredMatch objects ordered by score descending.

        Raises:
            SearchCapabilityError: If the field is not FTS-indexed.
        """
        if limit <= 0:
            limit = 100
        limit = min(limit, 1000)

        fts_table_name = f"fts_{entity_type.lower()}_{field_name.lower()}"

        with self._transaction() as conn:
            cursor = conn.cursor()

            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
                (fts_table_name,),
            )
            if cursor.fetchone() is None:
                raise SearchCapabilityError(
                    message=f"Field '{field_name}' on entity type '{entity_type}' is not FTS-indexed",
                    field_name=field_name,
                    entity_type=entity_type,
                )

            # Join the FTS table against the per-class typed table on
            # ``entity_id`` (the standard Hippo FTS column) so that
            # availability filtering happens on the per-class row. The
            # per-class table only holds rows of ``entity_type``, so an
            # explicit ``entity_type =`` predicate is unnecessary.
            cursor.execute(
                f"""SELECT pc.id, bm25({fts_table_name}) as bm25_score
                    FROM {fts_table_name} fts
                    INNER JOIN "{entity_type}" pc ON fts.entity_id = pc.id
                    WHERE {fts_table_name} MATCH ?
                    AND pc.is_available = 1
                    ORDER BY bm25_score
                    LIMIT ?""",
                (query, limit * 2),
            )

            results = []
            max_bm25 = None
            for row in cursor.fetchall():
                if max_bm25 is None:
                    max_bm25 = abs(row["bm25_score"]) if row["bm25_score"] != 0 else 1.0

                raw_bm25 = abs(row["bm25_score"]) if row["bm25_score"] != 0 else 0.0
                normalized = raw_bm25 / max_bm25 if max_bm25 > 0 else 0.0

                if normalized >= min_score:
                    results.append(
                        ScoredMatch(
                            entity_id=row["id"],
                            score=normalized,
                            highlights=None,
                        )
                    )

            results.sort(key=lambda x: x.score, reverse=True)
            return results[:limit]

    def create(
        self, entity: SQLiteEntity, user_context: Optional[str] = None
    ) -> SQLiteEntity:
        """Create a new entity in the store.

        Writes a typed row to the per-class table for ``entity.entity_type``,
        registers ``(uuid, class_name)`` in ``_entity_registry`` for fast
        cross-class lookup (sec9 §9.5), and records a ``create``
        ``ProvenanceRecord``.
        """
        import uuid

        entity_id = (
            entity.id if hasattr(entity, "id") and entity.id else str(uuid.uuid4())
        )
        entity_type = (
            entity.entity_type
            if hasattr(entity, "entity_type")
            else type(entity).__name__
        )

        entity_data = {}
        if hasattr(entity, "data") and isinstance(entity.data, dict):
            entity_data = entity.data
        else:
            for attr in dir(entity):
                if not attr.startswith("_"):
                    value = getattr(entity, attr, None)
                    if not callable(value):
                        entity_data[attr] = value

        is_available = (
            1 if not hasattr(entity, "is_available") or entity.is_available else 0
        )

        with self._transaction() as conn:
            cursor = conn.cursor()

            self._insert_per_class(cursor, entity_type, entity_id, entity_data,
                                   is_available=is_available)

            cursor.execute(
                "INSERT OR IGNORE INTO _entity_registry (uuid, class_name) "
                "VALUES (?, ?)",
                (entity_id, entity_type),
            )

            provenance = self._get_provenance_store(conn)
            provenance.record(
                entity_id=entity_id,
                entity_type=entity_type,
                operation="create",
                actor_id=user_context,
                patch=entity_data,
            )

        return entity

    def _insert_per_class(
        self,
        cursor: sqlite3.Cursor,
        entity_type: str,
        entity_id: str,
        data: dict[str, Any],
        is_available: int = 1,
        superseded_by: Optional[str] = None,
    ) -> None:
        """Insert a row into the per-class typed table when the class is known.

        No-op when the class is not in the user schema or is the
        hand-coded ``ProvenanceRecord``. ``id`` and ``is_available``
        are always set; user slot values come from ``data`` with
        unknown keys dropped.
        """
        if not self._per_class_table_exists(entity_type):
            return
        projected = self._project_to_columns(entity_type, data)
        columns: list[str] = ["id", "is_available", "superseded_by"]
        values: list[Any] = [entity_id, is_available, superseded_by]
        for name, value in projected.items():
            columns.append(name)
            values.append(self._coerce_for_column(value))
        column_sql = ", ".join(f'"{c}"' for c in columns)
        placeholders = ", ".join("?" for _ in columns)
        cursor.execute(
            f'INSERT INTO "{entity_type}" ({column_sql}) VALUES ({placeholders})',
            values,
        )

    def _update_per_class(
        self,
        cursor: sqlite3.Cursor,
        entity_type: str,
        entity_id: str,
        data: dict[str, Any],
    ) -> None:
        """Update user-slot columns on the per-class typed table.

        Replaces every user-slot column with the new value (including
        ``NULL`` for missing keys), mirroring the legacy semantics where
        ``entities.data`` was overwritten wholesale. System columns
        (``is_available``, ``superseded_by``) are handled by dedicated
        helpers. No-op when the class is not in the user schema.
        """
        if not self._per_class_table_exists(entity_type):
            return
        managed = {"id", "is_available", "superseded_by"}
        cols = [c for c in self._per_class_columns(entity_type) if c not in managed]
        if not cols:
            return
        sets = []
        params: list[Any] = []
        for c in cols:
            sets.append(f'"{c}" = ?')
            params.append(self._coerce_for_column(data.get(c)))
        params.append(entity_id)
        cursor.execute(
            f'UPDATE "{entity_type}" SET {", ".join(sets)} WHERE id = ?',
            params,
        )

    def _set_per_class_availability(
        self,
        cursor: sqlite3.Cursor,
        entity_type: str,
        entity_id: str,
        is_available: bool,
    ) -> None:
        """Flip ``is_available`` on the per-class table for one entity."""
        if not self._per_class_table_exists(entity_type):
            return
        cursor.execute(
            f'UPDATE "{entity_type}" SET "is_available" = ? WHERE id = ?',
            (1 if is_available else 0, entity_id),
        )

    def _set_per_class_superseded_by(
        self,
        cursor: sqlite3.Cursor,
        entity_type: str,
        entity_id: str,
        replacement_id: Optional[str],
        is_available: Optional[bool] = None,
    ) -> None:
        """Record a supersession pointer on the per-class table."""
        if not self._per_class_table_exists(entity_type):
            return
        if is_available is None:
            cursor.execute(
                f'UPDATE "{entity_type}" SET "superseded_by" = ? WHERE id = ?',
                (replacement_id, entity_id),
            )
        else:
            cursor.execute(
                f'UPDATE "{entity_type}" SET "superseded_by" = ?, "is_available" = ?'
                f" WHERE id = ?",
                (replacement_id, 1 if is_available else 0, entity_id),
            )

    def read(self, entity_id: str) -> Optional[SQLiteEntity]:
        """Read an entity by its ID (available entities only).

        Cross-class UUID lookup is served by ``_entity_registry``: the
        registered ``class_name`` for ``entity_id`` is read first, then
        the typed row comes from the per-class table. Returns ``None``
        when the entity is unknown or not currently available.
        """
        entity_type = self.resolve_type(entity_id)
        if entity_type is None:
            return None
        return self._read_per_class(entity_id, entity_type, only_available=True)

    def resolve_type(self, entity_id: str) -> Optional[str]:
        """Return the entity_type for a given UUID, or None if unknown.

        Looks up the class via the ``_entity_registry`` shadow table
        (sec9 §9.5). Includes entities regardless of availability — the
        type is still meaningful for archived / superseded rows.
        """
        with self._transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT class_name FROM _entity_registry WHERE uuid = ?",
                (entity_id,),
            )
            row = cursor.fetchone()
            return row["class_name"] if row else None

    def resolve_types(self, entity_ids: list[str]) -> dict[str, str]:
        """Batch variant of ``resolve_type``. Returns a dict keyed by id.

        Unknown UUIDs are absent from the returned dict (not raised). One
        SQL round-trip regardless of input size.
        """
        if not entity_ids:
            return {}
        with self._transaction() as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" for _ in entity_ids)
            cursor.execute(
                f"SELECT uuid, class_name FROM _entity_registry "
                f"WHERE uuid IN ({placeholders})",
                tuple(entity_ids),
            )
            return {row["uuid"]: row["class_name"] for row in cursor.fetchall()}

    def read_any(self, entity_id: str) -> Optional[SQLiteEntity]:
        """Read an entity by its ID, regardless of availability.

        This includes unavailable (soft-deleted, superseded) entities.
        """
        entity_type = self.resolve_type(entity_id)
        if entity_type is None:
            return None
        return self._read_per_class(entity_id, entity_type, only_available=False)

    def _read_per_class(
        self,
        entity_id: str,
        entity_type: str,
        only_available: bool,
    ) -> Optional[SQLiteEntity]:
        """Hydrate a SQLiteEntity from the per-class typed table.

        Returns ``None`` when the row is missing or (when
        ``only_available=True``) when it is unavailable. ``version`` is
        computed from the count of ``create``/``update`` ProvenanceRecord
        rows for the entity — see ``_compute_version``.
        """
        if not self._per_class_table_exists(entity_type):
            return None

        slot_columns = [
            c for c in self._per_class_columns(entity_type)
            if c not in {"id", "is_available", "superseded_by"}
        ]
        select_cols = ['"id"', '"is_available"', '"superseded_by"'] + [
            f'"{c}"' for c in slot_columns
        ]
        sql = (
            f"SELECT {', '.join(select_cols)} FROM \"{entity_type}\" "
            "WHERE id = ?"
        )
        if only_available:
            sql += " AND is_available = 1"

        with self._transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (entity_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            version = self._compute_version(cursor, entity_id)

        data = {
            c: self._decode_column_value(row[c]) for c in slot_columns
            if row[c] is not None
        }
        return SQLiteEntity(
            id=row["id"],
            entity_type=entity_type,
            is_available=bool(row["is_available"]),
            version=version,
            data=data,
            superseded_by=row["superseded_by"],
        )

    @staticmethod
    def _compute_version(cursor: sqlite3.Cursor, entity_id: str) -> int:
        """Derive the entity version from ProvenanceRecord.

        Counts the number of ``create``/``update`` records: the create
        gives version 1 and each subsequent update increments by 1. This
        replaces the legacy ``entities.version`` column dropped in PR 2.3.
        """
        cursor.execute(
            'SELECT COUNT(*) AS c FROM "ProvenanceRecord" '
            "WHERE entity_id = ? AND operation IN ('create', 'update')",
            (entity_id,),
        )
        row = cursor.fetchone()
        count = int(row["c"] if row else 0)
        return count if count > 0 else 1

    def update(self, entity: SQLiteEntity) -> SQLiteEntity:
        """Update an existing entity's typed columns.

        Performs a full-replacement update of the user-slot columns on
        the per-class typed table (when the class is known). Temporal
        tracking and version derivation live in ``ProvenanceRecord``;
        callers that want a provenance event must invoke ``update_data``
        or write the record themselves. This method is kept for protocol
        compliance and for callers that already produced their own
        ``ProvenanceRecord``.
        """
        entity_id = getattr(entity, "id", None)
        if not entity_id:
            return entity
        entity_type = getattr(entity, "entity_type", "") or ""
        data = getattr(entity, "data", None) or {}

        with self._transaction() as conn:
            cursor = conn.cursor()
            self._update_per_class(cursor, entity_type, entity_id, data)
        return entity

    def update_data(
        self,
        entity_id: str,
        entity_type: str,
        data: dict[str, Any],
        new_version: int,
        actor: Optional[str] = None,
        operation: str = "update",
    ) -> None:
        """Update typed columns and record provenance.

        Used by ``IngestionService._put_with_sqlite``/`_replace_with_sqlite`
        and the supersede paths. Version is no longer stored — it is
        derived on read from ``ProvenanceRecord`` (see
        ``_compute_version``); the ``new_version`` argument is accepted
        for API stability but has no persistent effect.
        """
        del new_version  # version is derived from ProvenanceRecord on read.
        with self._transaction() as conn:
            cursor = conn.cursor()
            self._update_per_class(cursor, entity_type, entity_id, data)

            provenance = self._get_provenance_store(conn)
            provenance.record(
                entity_id=entity_id,
                entity_type=entity_type,
                operation=operation,
                actor_id=actor,
                patch=data,
            )

    def set_availability(
        self,
        entity_id: str,
        entity_type: str,
        is_available: bool,
        actor: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> None:
        """Flip ``is_available`` on the per-class typed table.

        Records an ``availability_change`` provenance entry. Caller is
        responsible for ensuring the entity exists; this method does not
        raise on missing rows so that bulk loops can report per-entity
        success/failure.
        """
        with self._transaction() as conn:
            cursor = conn.cursor()
            self._set_per_class_availability(cursor, entity_type, entity_id, is_available)

            patch: dict[str, Any] = {"is_available": is_available}
            if reason is not None:
                patch["reason"] = reason
            provenance = self._get_provenance_store(conn)
            provenance.record(
                entity_id=entity_id,
                entity_type=entity_type,
                operation="availability_change",
                actor_id=actor,
                patch=patch,
            )

    def mark_superseded(
        self,
        entity_id: str,
        entity_type: str,
        replacement_id: str,
    ) -> None:
        """Mark an entity as superseded on the per-class typed table.

        Sets ``is_available = 0`` and ``superseded_by = replacement_id``
        on the per-class typed row. Provenance is the caller's
        responsibility — supersession currently writes multiple
        ``ProvenanceRecord`` rows around this mutation (sec9 §9.6) which
        would be awkward to inline here.
        """
        with self._transaction() as conn:
            cursor = conn.cursor()
            self._set_per_class_superseded_by(
                cursor, entity_type, entity_id, replacement_id, is_available=False
            )

    def delete(self, entity_id: str, user_context: Optional[str] = None) -> bool:
        """Delete an entity by its ID (soft delete).

        Looks up the entity's class via ``resolve_type``, flips
        ``is_available = 0`` on the per-class typed table, then records
        an ``availability_change`` provenance entry whose patch carries
        the original payload (for round-trip reconstruction). Returns
        ``False`` if the entity is unknown or already unavailable.
        """
        existing = self.read(entity_id)
        if existing is None:
            return False

        # ``id`` is a system column on the per-class table, not part of
        # ``existing.data``. Re-inject it so the soft-delete provenance
        # patch preserves the full entity payload for round-trip
        # reconstruction by callers that inspect ``patch.data``.
        snapshot = {"id": entity_id, **existing.data}

        with self._transaction() as conn:
            cursor = conn.cursor()
            self._set_per_class_availability(
                cursor, existing.entity_type, entity_id, False
            )

            provenance = self._get_provenance_store(conn)
            provenance.record(
                entity_id=entity_id,
                entity_type=existing.entity_type,
                operation="availability_change",
                actor_id=user_context,
                patch={
                    "status": "deleted",
                    "is_available": False,
                    "data": snapshot,
                },
            )

            return True

    def find(self, query: Query) -> Iterator[SQLiteEntity]:
        """Find entities matching a query.

        When ``query.entity_type`` is set the query targets the
        corresponding per-class typed table and filters on real columns;
        if the type is unknown to the schema, the result is empty.
        Without ``entity_type``, the adapter scans every concrete
        per-class table in the schema and merges results (cross-class
        scan).
        """
        if query.entity_type:
            if not self._per_class_table_exists(query.entity_type):
                return
            yield from self._find_per_class(query.entity_type, query)
            return

        registry = self.schema_registry
        if registry is None:
            return
        for class_name in registry.class_names():
            if not self._per_class_table_exists(class_name):
                continue
            yield from self._find_per_class(class_name, query)

    def _find_per_class(
        self, entity_type: str, query: Query
    ) -> Iterator[SQLiteEntity]:
        """Query a single per-class typed table.

        Filters become column-level predicates; ``data`` for the
        returned :class:`SQLiteEntity` is reconstructed from the typed
        row. ``version`` is derived from ``ProvenanceRecord`` (see
        ``_compute_version``).
        """
        slot_columns = [
            c for c in self._per_class_columns(entity_type)
            if c not in {"id", "is_available", "superseded_by"}
        ]
        select_cols = ['"id"', '"is_available"', '"superseded_by"'] + [
            f'"{c}"' for c in slot_columns
        ]
        sql = (
            f"SELECT {', '.join(select_cols)} FROM \"{entity_type}\" "
            "WHERE is_available = 1"
        )
        params: list[Any] = []

        valid_columns = set(slot_columns) | {"id", "is_available"}
        if query.filters:
            joiner = " OR " if getattr(query, "filter_mode", "and") == "or" else " AND "
            filter_clauses = []
            for f in query.filters:
                if "field" in f and "value" in f:
                    field = f["field"]
                    value = f["value"]
                    if field not in valid_columns:
                        return
                    filter_clauses.append(f'"{field}" = ?')
                    params.append(self._coerce_for_column(value))
                else:
                    for key, value in f.items():
                        if key not in valid_columns:
                            return
                        filter_clauses.append(f'"{key}" = ?')
                        params.append(self._coerce_for_column(value))
            if filter_clauses:
                sql += " AND (" + joiner.join(filter_clauses) + ")"

        if query.limit:
            sql += f" LIMIT {query.limit}"
            if query.offset:
                sql += f" OFFSET {query.offset}"
        elif query.offset:
            sql += f" LIMIT -1 OFFSET {query.offset}"

        with self._transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()

            version_map: dict[str, int] = {}
            row_ids = [r["id"] for r in rows]
            if row_ids:
                placeholders = ",".join("?" for _ in row_ids)
                cursor.execute(
                    f'SELECT entity_id, COUNT(*) AS c FROM "ProvenanceRecord" '
                    f"WHERE entity_id IN ({placeholders}) "
                    f"AND operation IN ('create', 'update') "
                    f"GROUP BY entity_id",
                    tuple(row_ids),
                )
                version_map = {
                    r["entity_id"]: int(r["c"]) for r in cursor.fetchall()
                }

        for row in rows:
            data = {
                c: self._decode_column_value(row[c]) for c in slot_columns
                if row[c] is not None
            }
            yield SQLiteEntity(
                id=row["id"],
                entity_type=entity_type,
                is_available=bool(row["is_available"]),
                version=version_map.get(row["id"], 1),
                data=data,
                superseded_by=row["superseded_by"],
            )

    @staticmethod
    def _decode_column_value(value: Any) -> Any:
        """Best-effort reverse of ``_coerce_for_column`` for query results.

        SQLite stores JSON-encoded containers and 0/1 booleans as text /
        integers; downstream consumers expect dict-shaped payloads with
        Python-native values. Strings that parse as JSON arrays/objects
        are decoded; other values pass through unchanged.
        """
        if isinstance(value, str) and value and value[0] in "[{":
            try:
                return json.loads(value)
            except (ValueError, TypeError):
                return value
        return value

    def findAll(self) -> Iterator[SQLiteEntity]:
        """Find all entities."""
        return self.find(Query())

    def findBy(self, **kwargs: Any) -> Iterator[SQLiteEntity]:
        """Find entities by field values."""
        query = Query()
        query.filters = [kwargs]
        return self.find(query)

    def track_creation(
        self, entity: SQLiteEntity, metadata: Dict[str, Any]
    ) -> ProvenanceRecordType:
        """Track the creation of an entity (in-memory record, no DB write)."""
        return ProvenanceRecordType(
            timestamp=datetime.now(timezone.utc),
            operation="create",
            entity_type=type(entity).__name__,
            entity_id=entity.id,
            actor_id="",
            schema_version="",
            patch=metadata,
        )

    def track_update(
        self, entity: SQLiteEntity, metadata: Dict[str, Any]
    ) -> ProvenanceRecordType:
        """Track the update of an entity (in-memory record, no DB write)."""
        return ProvenanceRecordType(
            timestamp=datetime.now(timezone.utc),
            operation="update",
            entity_type=type(entity).__name__,
            entity_id=entity.id,
            actor_id="",
            schema_version="",
            patch=metadata,
        )

    def track_deletion(
        self, entity_id: str, metadata: Dict[str, Any]
    ) -> ProvenanceRecordType:
        """Track the deletion of an entity (in-memory record, no DB write)."""
        return ProvenanceRecordType(
            timestamp=datetime.now(timezone.utc),
            operation="availability_change",
            entity_type="unknown",
            entity_id=entity_id,
            actor_id="",
            schema_version="",
            patch={"status": "deleted", **metadata},
        )

    def get_journal_mode(self) -> str:
        """Get the current journal mode."""
        with self._transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode")
            return cursor.fetchone()[0]

    def checkpoint(self) -> bool:
        """Execute a WAL checkpoint."""
        with self._transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA wal_checkpoint(FULL)")
            return cursor.fetchone()[0] == 1

    def get_wal_file_size(self) -> int:
        """Get the size of the WAL file if it exists."""
        wal_path = self.database_path.with_suffix(".db-wal")
        if wal_path.exists():
            return wal_path.stat().st_size
        return 0

    def close(self) -> None:
        """Close the database connection."""
        if hasattr(self._local, "connection") and self._local.connection:
            self._local.connection.close()
            self._local.connection = None

    def history(self, entity_id: str) -> list[dict[str, Any]]:
        """Get the change history for an entity.

        Args:
            entity_id: The ID of the entity.

        Returns:
            List of history records in chronological order.
        """
        with self._transaction() as conn:
            provenance = self._get_provenance_store(conn)
            return provenance.get_history(entity_id)

    def get_temporal(self, entity_ids: list[str]) -> "dict[str, TemporalRecord]":
        """Batch sec9 §9.7 temporal-field derivation. One SQL round-trip."""
        with self._transaction() as conn:
            provenance = self._get_provenance_store(conn)
            return provenance.get_temporal(entity_ids)

    def state_at(self, entity_id: str, timestamp: str) -> Optional[dict[str, Any]]:
        """Get the entity state at a specific point in time.

        Args:
            entity_id: The ID of the entity.
            timestamp: ISO format timestamp to query.

        Returns:
            The entity state at that time, or None if not found.
        """
        with self._transaction() as conn:
            provenance = self._get_provenance_store(conn)

            creation_time = provenance.get_entity_creation_time(entity_id)
            if creation_time is None:
                return None

            requested_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            creation_dt = datetime.fromisoformat(creation_time.replace("Z", "+00:00"))

            if requested_dt < creation_dt:
                from hippo.core.exceptions import TemporalQueryError

                raise TemporalQueryError(
                    message=f"Timestamp {timestamp} is before entity creation time {creation_time}",
                    entity_id=entity_id,
                    requested_timestamp=timestamp,
                    entity_creation_time=creation_time,
                )

            return provenance.get_state_at(entity_id, timestamp)

    def search_capabilities(self) -> set[str]:
        """Return the set of search modes supported by this adapter.

        The SQLite adapter supports full-text search (FTS5).

        Returns:
            A set containing "fts" to indicate FTS5 support.
        """
        return {"fts"}

    def explain_query(
        self, sql: str, params: Optional[list] = None
    ) -> list[dict[str, Any]]:
        """Explain the execution plan for a SQL query.

        This method uses SQLite's EXPLAIN QUERY PLAN functionality to analyze
        how a query will be executed, which helps determine if partial indexes
        are being utilized effectively.

        Args:
            sql: The SQL query to explain.
            params: Optional parameters for the query.

        Returns:
            List of dictionaries containing the execution plan details.
        """
        with self._transaction() as conn:
            cursor = conn.cursor()

            # Use EXPLAIN QUERY PLAN to analyze the plan
            explain_sql = f"EXPLAIN QUERY PLAN {sql}"

            if params:
                cursor.execute(explain_sql, params)
            else:
                cursor.execute(explain_sql)

            results = []
            for row in cursor.fetchall():
                results.append(
                    {
                        "selectid": row["selectid"],
                        "order": row["order"],
                        "from": row["from"],
                        "detail": row["detail"],
                    }
                )

            return results
