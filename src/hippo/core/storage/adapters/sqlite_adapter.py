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

    def __init__(
        self,
        database_path: str | Path,
        wal_mode: bool = True,
        schema_version: Optional[str] = None,
    ):
        """Initialize the SQLite adapter.

        Args:
            database_path: Path to the SQLite database file.
            wal_mode: Whether to enable WAL journal mode.
            schema_version: Schema version string captured on each
                ``ProvenanceRecord`` write (sec9 §9.6 / §9.7). Typically
                derived from ``SchemaRegistry.schema_view.schema.version``
                by ``HippoClient``; callers constructing the adapter
                directly may supply it explicitly. Defaults to the empty
                string (legacy transition; see Decision 9.6.F).
        """
        self.database_path = Path(database_path)
        self.wal_mode = wal_mode
        self._schema_version = schema_version or ""
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
                    data TEXT NOT NULL
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

        # System column: superseded_by (nullable, applied generically to entities table)
        # This is analogous to is_available — a system field present on all entities.
        cursor.execute("PRAGMA table_info(entities)")
        entity_columns = {row[1] for row in cursor.fetchall()}
        if "superseded_by" not in entity_columns:
            cursor.execute("ALTER TABLE entities ADD COLUMN superseded_by TEXT")

        # Phase E: drop legacy stored temporal columns (PTS-69).
        # Temporal fields are now computed exclusively from ProvenanceRecord
        # via entity_provenance_summary / get_temporal(). SQLite 3.35+ supports
        # ALTER TABLE … DROP COLUMN. Guarded by PRAGMA table_info so the
        # migration is idempotent.
        for col in ("created_at", "updated_at"):
            if col in entity_columns:
                cursor.execute(f"ALTER TABLE entities DROP COLUMN {col}")

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

            cursor.execute(
                """INSERT INTO entities (id, entity_type, is_available, version, data)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    entity_id,
                    entity_type,
                    1,
                    entity.version if hasattr(entity, "version") else 1,
                    json.dumps(entity_data),
                ),
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

    def read(self, entity_id: str) -> Optional[SQLiteEntity]:
        """Read an entity by its ID (available entities only)."""
        with self._transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, entity_type, is_available, version, data, superseded_by
                   FROM entities WHERE id = ? AND is_available = 1""",
                (entity_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None

            return self._row_to_entity(row)

    def resolve_type(self, entity_id: str) -> Optional[str]:
        """Return the entity_type for a given UUID, or None if unknown.

        Looks up the `entities` table's type discriminator. Includes entities
        regardless of availability — the type is still meaningful for
        archived / superseded rows. Per sec9 §9.5's identity model, this is
        the relational adapter's implementation of UUID → type resolution.
        """
        with self._transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT entity_type FROM entities WHERE id = ?",
                (entity_id,),
            )
            row = cursor.fetchone()
            return row["entity_type"] if row else None

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
                f"SELECT id, entity_type FROM entities WHERE id IN ({placeholders})",
                tuple(entity_ids),
            )
            return {row["id"]: row["entity_type"] for row in cursor.fetchall()}

    def read_any(self, entity_id: str) -> Optional[SQLiteEntity]:
        """Read an entity by its ID, regardless of availability.

        This includes unavailable (soft-deleted, superseded) entities.
        """
        with self._transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, entity_type, is_available, version, data, superseded_by
                   FROM entities WHERE id = ?""",
                (entity_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None

            return self._row_to_entity(row)

    def update(self, entity: SQLiteEntity) -> SQLiteEntity:
        """Update an existing entity (no-op on entities table; temporal tracking is via ProvenanceRecord)."""
        return entity

    def delete(self, entity_id: str, user_context: Optional[str] = None) -> bool:
        """Delete an entity by its ID (soft delete)."""
        with self._transaction() as conn:
            cursor = conn.cursor()

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
                """UPDATE entities SET is_available = 0
                   WHERE id = ? AND is_available = 1""",
                (entity_id,),
            )

            provenance = self._get_provenance_store(conn)
            provenance.record(
                entity_id=entity_id,
                entity_type=entity_type,
                operation="availability_change",
                actor_id=user_context,
                patch={"status": "deleted", "is_available": False, "data": original_data},
            )

            return True

    def find(self, query: Query) -> Iterator[SQLiteEntity]:
        """Find entities matching a query."""
        with self._transaction() as conn:
            cursor = conn.cursor()

            sql = "SELECT id, entity_type, is_available, version, data, superseded_by FROM entities WHERE is_available = 1"
            params = []

            if query.entity_type:
                sql += " AND entity_type = ?"
                params.append(query.entity_type)

            if query.filters:
                joiner = " OR " if getattr(query, "filter_mode", "and") == "or" else " AND "
                filter_clauses = []
                for f in query.filters:
                    if "field" in f and "value" in f:
                        # Structured filter: {"field": "name", "operator": "eq", "value": "x"}
                        field = f["field"]
                        value = f["value"]
                        filter_clauses.append("json_extract(data, ?) = ?")
                        params.append(f"$.{field}")
                        params.append(value)
                    else:
                        # Simple filter: {"name": "Alpha"}
                        for key, value in f.items():
                            filter_clauses.append("json_extract(data, ?) = ?")
                            params.append(f"$.{key}")
                            params.append(value)
                if filter_clauses:
                    sql += " AND (" + joiner.join(filter_clauses) + ")"

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
        # superseded_by column may not exist in older deployments pre-migration.
        try:
            superseded_by = row["superseded_by"]
        except IndexError:
            superseded_by = None
        return SQLiteEntity(
            id=row["id"],
            entity_type=row["entity_type"],
            is_available=bool(row["is_available"]),
            version=row["version"],
            data=json.loads(row["data"]) if row["data"] else {},
            superseded_by=superseded_by,
        )

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
