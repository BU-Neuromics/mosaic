"""SQLite storage adapter with WAL mode support.

The SQLite adapter provides:
- WAL mode for improved concurrency
- Automatic trigger creation for provenance immutability
- Thread-safe connection management

## Provenance Immutability Triggers

The adapter automatically creates BEFORE triggers on the provenance table to enforce
immutability at the database level:

- `prevent_provenance_pk_update`: Blocks updates to entity_id (primary key)
- `prevent_provenance_timestamp_update`: Blocks updates to timestamp field
- `prevent_provenance_metadata_update`: Blocks updates to user_context field
- `prevent_provenance_content_update`: Blocks updates to payload field
- `prevent_provenance_delete`: Blocks DELETE operations on provenance records

Triggers use `CREATE TRIGGER IF NOT EXISTS` for idempotent initialization.
"""

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, Iterator, List, Optional

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
from hippo.core.types import ProvenanceRecord as ProvenanceRecordType
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
        created_at: str,
        updated_at: Optional[str],
    ):
        self.id = id
        self.entity_type = entity_type
        self.is_available = is_available
        self.version = version
        self.data = data
        self.created_at = created_at
        self.updated_at = updated_at


class ProvenanceStore:
    """Store for provenance records in SQLite."""

    def __init__(self, connection: sqlite3.Connection):
        self._conn = connection

    @staticmethod
    def compute_state_hash(data: dict[str, Any]) -> str:
        """Compute SHA-256 hash of entity state.

        Args:
            data: The entity data to hash.

        Returns:
            Hexadecimal string representation of the SHA-256 hash.
        """
        import hashlib

        serialized = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()

    @staticmethod
    def generate_operation_id() -> str:
        """Generate a unique operation ID.

        Returns:
            UUID string for the operation.
        """
        import uuid

        return str(uuid.uuid4())

    def record(
        self,
        entity_id: str,
        entity_type: str,
        operation_type: str,
        user_context: Optional[str],
        payload: dict[str, Any],
        operation_id: Optional[str] = None,
        previous_state_hash: Optional[str] = None,
        state_snapshot: Optional[dict[str, Any]] = None,
    ) -> ProvenanceRecordType:
        """Record a provenance event."""
        from hippo.core.types import ProvenanceRecord

        now = datetime.now(timezone.utc)

        if operation_id is None:
            operation_id = self.generate_operation_id()

        if previous_state_hash is None and payload:
            previous_state_hash = self.compute_state_hash(payload)

        if state_snapshot is None:
            state_snapshot = payload

        record = ProvenanceRecord(
            source="sqlite_adapter",
            timestamp=now,
            operation=operation_type,
            entity_type=entity_type,
            entity_id=entity_id,
            user_context=user_context,
            payload=payload,
        )

        cursor = self._conn.cursor()
        cursor.execute(
            """INSERT INTO provenance (entity_id, entity_type, operation_type, timestamp, user_context, payload, operation_id, previous_state_hash, state_snapshot)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entity_id,
                entity_type,
                operation_type,
                now.isoformat(),
                user_context,
                json.dumps(payload),
                operation_id,
                previous_state_hash,
                json.dumps(state_snapshot) if state_snapshot else None,
            ),
        )

        return record

    def find_by_entity(
        self, entity_id: str, operation_type: Optional[str] = None
    ) -> Iterator[ProvenanceRecordType]:
        """Find provenance records for an entity."""
        cursor = self._conn.cursor()

        sql = "SELECT * FROM provenance WHERE entity_id = ?"
        params = [entity_id]

        if operation_type:
            sql += " AND operation_type = ?"
            params.append(operation_type)

        sql += " ORDER BY timestamp DESC"

        cursor.execute(sql, params)
        for row in cursor.fetchall():
            yield ProvenanceRecordType(
                source=row["source"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                operation=row["operation_type"],
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                user_context=row["user_context"],
                payload=json.loads(row["payload"]) if row["payload"] else {},
            )

    def get_history(self, entity_id: str) -> list[dict[str, Any]]:
        """Get the complete change history for an entity.

        Args:
            entity_id: The ID of the entity.

        Returns:
            List of provenance records in chronological order (oldest first).
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """SELECT operation_id, entity_id, entity_type, operation_type, timestamp, 
                      user_context, previous_state_hash, state_snapshot
               FROM provenance 
               WHERE entity_id = ? 
               ORDER BY timestamp ASC""",
            (entity_id,),
        )

        results = []
        for row in cursor.fetchall():
            results.append(
                {
                    "operation_id": row["operation_id"],
                    "entity_id": row["entity_id"],
                    "entity_type": row["entity_type"],
                    "operation_type": row["operation_type"],
                    "timestamp": row["timestamp"],
                    "user_id": row["user_context"],
                    "previous_state_hash": row["previous_state_hash"],
                    "state_snapshot": json.loads(row["state_snapshot"])
                    if row["state_snapshot"]
                    else None,
                }
            )

        return results

    def get_state_at(self, entity_id: str, timestamp: str) -> Optional[dict[str, Any]]:
        """Get the entity state at a specific point in time.

        Args:
            entity_id: The ID of the entity.
            timestamp: ISO format timestamp to query.

        Returns:
            The entity state at that time, or None if entity didn't exist yet.
        """
        cursor = self._conn.cursor()

        cursor.execute(
            """SELECT state_snapshot, timestamp, operation_type
               FROM provenance 
               WHERE entity_id = ? AND timestamp <= ?
               ORDER BY timestamp DESC
               LIMIT 1""",
            (entity_id, timestamp),
        )

        row = cursor.fetchone()
        if row is None:
            return None

        if row["operation_type"] == "SOFT_DELETE":
            return None

        return {
            "entity_id": entity_id,
            "state": json.loads(row["state_snapshot"])
            if row["state_snapshot"]
            else None,
            "timestamp": row["timestamp"],
        }

    def get_entity_creation_time(self, entity_id: str) -> Optional[str]:
        """Get the creation timestamp of an entity.

        Args:
            entity_id: The ID of the entity.

        Returns:
            ISO format timestamp of entity creation, or None if not found.
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """SELECT timestamp FROM provenance 
               WHERE entity_id = ? AND operation_type = 'CREATE'
               ORDER BY timestamp ASC
               LIMIT 1""",
            (entity_id,),
        )
        row = cursor.fetchone()
        return row["timestamp"] if row else None


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


class ExternalIdRecord:
    """External ID record."""

    def __init__(
        self,
        id: str,
        entity_id: str,
        external_id: str,
        created_at: str,
        superseded_at: Optional[str] = None,
    ):
        self.id = id
        self.entity_id = entity_id
        self.external_id = external_id
        self.created_at = created_at
        self.superseded_at = superseded_at


class ExternalIdStorageAdapter:
    """Storage adapter for managing external IDs."""

    def __init__(self, connection: sqlite3.Connection):
        self._conn = connection

    def create_external_id(self, entity_id: str, external_id: str) -> ExternalIdRecord:
        """Create a new external ID for an entity."""
        import uuid

        now = datetime.now(timezone.utc).isoformat()
        record_id = str(uuid.uuid4())

        cursor = self._conn.cursor()
        cursor.execute(
            """INSERT INTO entity_external_ids (id, entity_id, external_id, created_at, superseded_at)
               VALUES (?, ?, ?, ?, NULL)""",
            (record_id, entity_id, external_id, now),
        )

        return ExternalIdRecord(
            id=record_id,
            entity_id=entity_id,
            external_id=external_id,
            created_at=now,
            superseded_at=None,
        )

    def get_entity_by_external_id(
        self, external_id: str, include_archived: bool = False
    ) -> Optional[ExternalIdRecord]:
        """Get the entity by external ID, returning the latest (by created_at)."""
        cursor = self._conn.cursor()

        if include_archived:
            cursor.execute(
                """SELECT * FROM entity_external_ids
                   WHERE external_id = ? AND superseded_at IS NULL
                   ORDER BY created_at DESC
                   LIMIT 1""",
                (external_id,),
            )
        else:
            cursor.execute(
                """SELECT eei.* FROM entity_external_ids eei
                   INNER JOIN entities e ON eei.entity_id = e.id
                   WHERE eei.external_id = ? AND e.is_available = 1 AND eei.superseded_at IS NULL
                   ORDER BY eei.created_at DESC
                   LIMIT 1""",
                (external_id,),
            )

        row = cursor.fetchone()
        if row is None:
            return None

        return self._row_to_external_id(row)

    def list_external_ids_for_entity(
        self, entity_id: str, include_superseded: bool = False
    ) -> Iterator[ExternalIdRecord]:
        """List all external IDs for an entity."""
        cursor = self._conn.cursor()

        if include_superseded:
            cursor.execute(
                """SELECT * FROM entity_external_ids
                   WHERE entity_id = ?
                   ORDER BY created_at DESC""",
                (entity_id,),
            )
        else:
            cursor.execute(
                """SELECT * FROM entity_external_ids
                   WHERE entity_id = ? AND superseded_at IS NULL
                   ORDER BY created_at DESC""",
                (entity_id,),
            )

        for row in cursor.fetchall():
            yield self._row_to_external_id(row)

    def supersede_external_id(
        self, entity_id: str, old_external_id: str, new_external_id: str
    ) -> ExternalIdRecord:
        """Supersede an external ID with a new one."""
        import uuid

        now = datetime.now(timezone.utc).isoformat()
        new_record_id = str(uuid.uuid4())

        cursor = self._conn.cursor()

        cursor.execute(
            """UPDATE entity_external_ids
               SET superseded_at = ?
               WHERE entity_id = ? AND external_id = ? AND superseded_at IS NULL""",
            (now, entity_id, old_external_id),
        )

        cursor.execute(
            """INSERT INTO entity_external_ids (id, entity_id, external_id, created_at, superseded_at)
               VALUES (?, ?, ?, ?, NULL)""",
            (new_record_id, entity_id, new_external_id, now),
        )

        return ExternalIdRecord(
            id=new_record_id,
            entity_id=entity_id,
            external_id=new_external_id,
            created_at=now,
            superseded_at=None,
        )

    def _row_to_external_id(self, row: sqlite3.Row) -> ExternalIdRecord:
        """Convert a database row to an ExternalIdRecord."""
        return ExternalIdRecord(
            id=row["id"],
            entity_id=row["entity_id"],
            external_id=row["external_id"],
            created_at=row["created_at"],
            superseded_at=row["superseded_at"],
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


class SQLiteAdapter(EntityStore[SQLiteEntity]):
    """SQLite storage adapter with WAL mode for improved concurrency."""

    def __init__(self, database_path: str | Path, wal_mode: bool = True):
        self.database_path = Path(database_path)
        self.wal_mode = wal_mode
        self._local = threading.local()
        self._provenance_store: Optional[ProvenanceStore] = None
        self._relationship_store: Optional[RelationshipStore] = None
        self._external_id_store: Optional[ExternalIdStorageAdapter] = None
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

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    is_available INTEGER NOT NULL DEFAULT 1,
                    version INTEGER NOT NULL DEFAULT 1,
                    data TEXT NOT NULL,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_entities_type
                ON entities(entity_type)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_entities_available
                ON entities(is_available)
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS provenance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    operation_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    user_context TEXT,
                    payload TEXT,
                    operation_id TEXT,
                    previous_state_hash TEXT,
                    state_snapshot TEXT
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_provenance_entity_id
                ON provenance(entity_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_provenance_operation_type
                ON provenance(operation_type)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_provenance_timestamp
                ON provenance(timestamp)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_provenance_entity_timestamp
                ON provenance(entity_id, timestamp)
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

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entity_external_ids (
                    id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    superseded_at TEXT,
                    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_entity_external_ids_entity
                ON entity_external_ids(entity_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_entity_external_ids_external
                ON entity_external_ids(external_id, created_at DESC)
            """)

            self._init_triggers(cursor)

            self._run_migrations(cursor)

    def _init_triggers(self, cursor: sqlite3.Cursor) -> None:
        """Initialize provenance immutability triggers."""
        for trigger_sql in sqlite_triggers.get_trigger_sql_list():
            cursor.execute(trigger_sql)

    def _run_migrations(self, cursor: sqlite3.Cursor) -> None:
        """Run database migrations for schema updates."""
        cursor.execute("PRAGMA table_info(provenance)")
        columns = {row[1] for row in cursor.fetchall()}

        if "operation_id" not in columns:
            cursor.execute("ALTER TABLE provenance ADD COLUMN operation_id TEXT")

        if "previous_state_hash" not in columns:
            cursor.execute("ALTER TABLE provenance ADD COLUMN previous_state_hash TEXT")

        if "state_snapshot" not in columns:
            cursor.execute("ALTER TABLE provenance ADD COLUMN state_snapshot TEXT")

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_provenance_entity_timestamp'"
        )
        if cursor.fetchone() is None:
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_provenance_entity_timestamp ON provenance(entity_id, timestamp)"
            )

    def _get_provenance_store(self, conn: sqlite3.Connection) -> ProvenanceStore:
        """Get or create a ProvenanceStore for the given connection."""
        if self._provenance_store is None:
            self._provenance_store = ProvenanceStore(conn)
        return self._provenance_store

    def _get_relationship_store(self, conn: sqlite3.Connection) -> RelationshipStore:
        """Get or create a RelationshipStore for the given connection."""
        if self._relationship_store is None:
            self._relationship_store = RelationshipStore(conn)
        return self._relationship_store

    def _get_external_id_store(
        self, conn: Optional[sqlite3.Connection] = None
    ) -> ExternalIdStorageAdapter:
        """Get or create an ExternalIdStorageAdapter."""
        if conn is None:
            conn = self._get_connection()
        if self._external_id_store is None:
            self._external_id_store = ExternalIdStorageAdapter(conn)
        return self._external_id_store

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
        content_table: str = "entities",
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

            cursor.execute(
                f"""SELECT e.id, bm25({fts_table_name}) as bm25_score
                    FROM {fts_table_name} fts
                    INNER JOIN entities e ON fts.rowid = e.rowid
                    WHERE {fts_table_name} MATCH ?
                    AND e.entity_type = ?
                    AND e.is_available = 1
                    ORDER BY bm25_score
                    LIMIT ?""",
                (query, entity_type, limit * 2),
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
        """Create a new entity in the store."""
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

        with self._transaction() as conn:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()

            cursor.execute(
                """INSERT INTO entities (id, entity_type, is_available, version, data, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    entity_id,
                    entity_type,
                    1,
                    entity.version if hasattr(entity, "version") else 1,
                    json.dumps(entity_data),
                    now,
                    now,
                ),
            )

            provenance = self._get_provenance_store(conn)
            provenance.record(
                entity_id=entity_id,
                entity_type=entity_type,
                operation_type="CREATE",
                user_context=user_context,
                payload=entity_data,
            )

        return entity

    def read(self, entity_id: str) -> Optional[SQLiteEntity]:
        """Read an entity by its ID."""
        with self._transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, entity_type, is_available, version, data, created_at, updated_at
                   FROM entities WHERE id = ? AND is_available = 1""",
                (entity_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None

            return self._row_to_entity(row)

    def update(self, entity: SQLiteEntity) -> SQLiteEntity:
        """Update an existing entity."""
        from datetime import datetime, timezone

        with self._transaction() as conn:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """UPDATE entities SET updated_at = ? WHERE id = ? AND is_available = 1""",
                (now, entity.id),
            )

        return entity

    def delete(self, entity_id: str, user_context: Optional[str] = None) -> bool:
        """Delete an entity by its ID (soft delete)."""
        with self._transaction() as conn:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()

            cursor.execute(
                "SELECT id, entity_type, data FROM entities WHERE id = ? AND is_available = 1",
                (entity_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return False

            entity_type = row["entity_type"]
            original_data = json.loads(row["data"]) if row["data"] else {}

            cursor.execute(
                """UPDATE entities SET is_available = 0, updated_at = ?
                   WHERE id = ? AND is_available = 1""",
                (now, entity_id),
            )

            provenance = self._get_provenance_store(conn)
            provenance.record(
                entity_id=entity_id,
                entity_type=entity_type,
                operation_type="SOFT_DELETE",
                user_context=user_context,
                payload=original_data,
            )

            return True

    def find(self, query: Query) -> Iterator[SQLiteEntity]:
        """Find entities matching a query."""
        with self._transaction() as conn:
            cursor = conn.cursor()

            sql = "SELECT id, entity_type, is_available, version, data, created_at, updated_at FROM entities WHERE is_available = 1"
            params = []

            if query.entity_type:
                sql += " AND entity_type = ?"
                params.append(query.entity_type)

            if query.filters:
                for f in query.filters:
                    for key, value in f.items():
                        sql += " AND data LIKE ?"
                        params.append(f"%{key}%")

            if query.limit:
                sql += f" LIMIT {query.limit}"
                if query.offset:
                    sql += f" OFFSET {query.offset}"
            elif query.offset:
                sql += f" LIMIT -1 OFFSET {query.offset}"

            cursor.execute(sql, params)
            for row in cursor.fetchall():
                yield self._row_to_entity(row)

    def findAll(self) -> Iterator[SQLiteEntity]:
        """Find all entities."""
        return self.find(Query())

    def findBy(self, **kwargs: Any) -> Iterator[SQLiteEntity]:
        """Find entities by field values."""
        query = Query()
        query.filters = [kwargs]
        return self.find(query)

    def _row_to_entity(self, row: sqlite3.Row) -> "SQLiteEntity":
        """Convert a database row to an entity."""
        return SQLiteEntity(
            id=row["id"],
            entity_type=row["entity_type"],
            is_available=bool(row["is_available"]),
            version=row["version"],
            data=json.loads(row["data"]) if row["data"] else {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def track_creation(
        self, entity: SQLiteEntity, metadata: Dict[str, Any]
    ) -> ProvenanceRecordType:
        """Track the creation of an entity."""
        record = ProvenanceRecordType(
            source="sqlite_adapter",
            timestamp=datetime.now(timezone.utc),
            operation="create",
            entity_type=type(entity).__name__,
            entity_id=entity.id,
            user_context=None,
            payload=metadata,
        )
        return record

    def track_update(
        self, entity: SQLiteEntity, metadata: Dict[str, Any]
    ) -> ProvenanceRecordType:
        """Track the update of an entity."""
        record = ProvenanceRecordType(
            source="sqlite_adapter",
            timestamp=datetime.now(timezone.utc),
            operation="update",
            entity_type=type(entity).__name__,
            entity_id=entity.id,
            user_context=None,
            payload=metadata,
        )
        return record

    def track_deletion(
        self, entity_id: str, metadata: Dict[str, Any]
    ) -> ProvenanceRecordType:
        """Track the deletion of an entity."""
        record = ProvenanceRecordType(
            source="sqlite_adapter",
            timestamp=datetime.now(timezone.utc),
            operation="delete",
            entity_type="unknown",
            entity_id=entity_id,
            user_context=None,
            payload=metadata,
        )
        return record

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
