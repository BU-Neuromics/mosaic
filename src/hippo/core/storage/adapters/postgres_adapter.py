"""PostgreSQL storage adapter with connection pooling and full-text search.

The PostgreSQL adapter provides:
- Connection pooling via psycopg3 (psycopg[pool])
- Full-text search using tsvector/tsquery with BM25-like ranking
- Trigram similarity for fuzzy matching (pg_trgm extension)
- Atomic upserts for multi-instance safety (INSERT ... ON CONFLICT)
- Provenance immutability via database triggers

## Provenance Immutability

The adapter creates BEFORE triggers on the provenance table to enforce
immutability at the database level, mirroring the SQLite adapter's guarantees:

- Blocks UPDATE on entity_id, timestamp, user_context, payload columns
- Blocks DELETE operations on provenance records
"""

import json
import hashlib
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Generator, Iterator, List, Optional

from hippo.core.storage import EntityStore, Query, ScoredMatch
from hippo.core.types import ProvenanceRecord as ProvenanceRecordType, TemporalRecord
from hippo.core.exceptions import AdapterError, SearchCapabilityError

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
except ImportError:
    raise ImportError(
        "PostgreSQL adapter requires psycopg[pool]. "
        "Install with: pip install hippo[postgres]"
    )


class PostgresEntity:
    """Entity stored in PostgreSQL."""

    def __init__(
        self,
        id: str,
        entity_type: str,
        is_available: bool,
        version: int,
        data: dict[str, Any],
        created_at: str,
        updated_at: Optional[str],
        superseded_by: Optional[str] = None,
    ):
        self.id = id
        self.entity_type = entity_type
        self.is_available = is_available
        self.version = version
        self.data = data
        self.created_at = created_at
        self.updated_at = updated_at
        self.superseded_by = superseded_by


from hippo.core.storage.adapters.sqlite_adapter import (
    _LEGACY_OPERATION_MAP as _PG_LEGACY_OPERATION_MAP,  # noqa: F401
    _normalize_operation as _pg_normalize_operation,
)


class PostgresProvenanceStore:
    """Postgres sibling of ``ProvenanceStore`` on the ``ProvenanceRecord`` table.

    Mirrors the SQLite store's sec9 §9.6 shape. SQL-level
    append-only enforcement is handled by a BEFORE UPDATE / BEFORE DELETE
    trigger equivalent to the SQLite one (Decision 9.6.C).
    """

    def __init__(self, conn: psycopg.Connection, schema_version: Optional[str] = None):
        self._conn = conn
        self._schema_version = schema_version or ""

    def record(
        self,
        entity_id: Optional[str],
        entity_type: Optional[str],
        operation: Any = None,
        actor_id: Optional[str] = None,
        patch: Optional[dict[str, Any]] = None,
        context: Optional[dict[str, Any]] = None,
        derived_from_id: Optional[str] = None,
        process_id: Optional[str] = None,
        schema_version: Optional[str] = None,
        # Legacy kwargs (Decision 9.6.B)
        operation_type: Any = None,
        user_context: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
        operation_id: Optional[str] = None,  # noqa: ARG002
        previous_state_hash: Optional[str] = None,  # noqa: ARG002
        state_snapshot: Optional[dict[str, Any]] = None,  # noqa: ARG002
    ) -> ProvenanceRecordType:
        op_source = operation if operation is not None else operation_type
        if op_source is None:
            raise ValueError("operation (or legacy operation_type) is required")
        op_value = _pg_normalize_operation(op_source)

        # actor_id resolution order (Decision 9.6.G): explicit kwarg → legacy
        # user_context shim → ContextVar (middleware / with_actor()) → sentinel.
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

        cur = self._conn.cursor()
        cur.execute(
            """INSERT INTO "ProvenanceRecord"
               (id, entity_id, entity_type, operation, actor_id, timestamp,
                schema_version, derived_from_id, process_id, patch, context,
                is_available)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)""",
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
        return ProvenanceRecordType(
            id=record_id,
            entity_id=entity_id,
            entity_type=entity_type,
            operation=op_value,
            actor_id=effective_actor or "",
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
        operation_type: Any = None,
    ) -> Iterator[ProvenanceRecordType]:
        op_filter = operation if operation is not None else operation_type
        cur = self._conn.cursor()
        sql = 'SELECT * FROM "ProvenanceRecord" WHERE entity_id = %s'
        params: list[Any] = [entity_id]

        if op_filter is not None:
            sql += " AND operation = %s"
            params.append(_pg_normalize_operation(op_filter))

        sql += " ORDER BY timestamp DESC"
        cur.execute(sql, params)

        for row in cur.fetchall():
            yield ProvenanceRecordType(
                id=row["id"],
                entity_id=row["entity_id"],
                entity_type=row["entity_type"],
                operation=row["operation"],
                actor_id=row["actor_id"] or "",
                timestamp=datetime.fromisoformat(row["timestamp"]) if isinstance(row["timestamp"], str) else row["timestamp"],
                schema_version=row["schema_version"] or "",
                derived_from_id=row["derived_from_id"],
                process_id=row["process_id"],
                patch=json.loads(row["patch"]) if isinstance(row["patch"], str) and row["patch"] else row["patch"],
                context=json.loads(row["context"]) if isinstance(row["context"], str) and row["context"] else row["context"],
            )

    def get_history(self, entity_id: str) -> list[dict[str, Any]]:
        cur = self._conn.cursor()
        cur.execute(
            """SELECT id, entity_id, entity_type, operation, timestamp,
                      actor_id, patch
               FROM "ProvenanceRecord"
               WHERE entity_id = %s
               ORDER BY timestamp ASC""",
            (entity_id,),
        )
        results = []
        for row in cur.fetchall():
            patch = row["patch"]
            if isinstance(patch, str):
                patch = json.loads(patch) if patch else None
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
        cur = self._conn.cursor()
        cur.execute(
            """SELECT patch, timestamp, operation
               FROM "ProvenanceRecord"
               WHERE entity_id = %s AND timestamp <= %s
               ORDER BY timestamp DESC
               LIMIT 1""",
            (entity_id, timestamp),
        )

        row = cur.fetchone()
        if row is None:
            return None

        patch_val = row["patch"]
        if isinstance(patch_val, str):
            patch_val = json.loads(patch_val) if patch_val else None

        if row["operation"] == "availability_change" and isinstance(patch_val, dict):
            if (
                patch_val.get("status") == "deleted"
                or patch_val.get("is_available") is False
            ):
                return None

        return {
            "entity_id": entity_id,
            "state": patch_val,
            "timestamp": row["timestamp"],
        }

    def get_entity_creation_time(self, entity_id: str) -> Optional[str]:
        cur = self._conn.cursor()
        cur.execute(
            """SELECT timestamp FROM "ProvenanceRecord"
               WHERE entity_id = %s AND operation = 'create'
               ORDER BY timestamp ASC
               LIMIT 1""",
            (entity_id,),
        )
        row = cur.fetchone()
        return row["timestamp"] if row else None

    def get_provenance_timestamps(
        self, entity_id: str
    ) -> Optional[dict[str, Optional[str]]]:
        """Legacy single-entity timestamp derivation. Delegates to get_temporal."""
        out = self.get_temporal([entity_id])
        if entity_id not in out:
            return None
        rec = out[entity_id]
        return {"created_at": rec.created_at, "updated_at": rec.updated_at}

    def get_temporal(
        self, entity_ids: list[str]
    ) -> "dict[str, TemporalRecord]":
        """Batch sec9 §9.7 temporal derivation (Postgres mirror of the SQLite path)."""
        from hippo.core.types import TemporalRecord

        if not entity_ids:
            return {}

        cur = self._conn.cursor()
        cur.execute(
            """WITH target AS (
                    SELECT entity_id, operation, timestamp, actor_id,
                           schema_version, patch
                    FROM "ProvenanceRecord"
                    WHERE entity_id = ANY(%s)
                ),
                agg AS (
                    SELECT
                        entity_id,
                        MIN(CASE WHEN operation = 'create'
                                 THEN timestamp END) AS created_at,
                        MAX(CASE
                            WHEN operation = 'availability_change'
                                 AND (patch::jsonb->>'status' = 'deleted'
                                      OR patch::jsonb->>'is_available' = 'false')
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
            (list(entity_ids),),
        )

        result: dict[str, TemporalRecord] = {}
        for row in cur.fetchall():
            eid = row["entity_id"]
            result[eid] = TemporalRecord(
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                schema_version=row["schema_version"] or None,
                created_by=row["created_by"] or None,
                updated_by=row["updated_by"] or None,
            )
        return result


class PostgresRelationshipRecord:
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


class PostgresRelationshipStore:
    """Store for relationship records in PostgreSQL."""

    def __init__(self, conn: psycopg.Connection):
        self._conn = conn

    def create(
        self,
        source_id: str,
        target_id: str,
        relationship_type: str,
        created_by: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> PostgresRelationshipRecord:
        now = datetime.now(timezone.utc).isoformat()
        rel_id = str(uuid.uuid4())

        cur = self._conn.cursor()
        cur.execute(
            """INSERT INTO relationships
               (id, source_id, target_id, relationship_type, metadata, created_at, created_by, is_available)
               VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE)""",
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

        return PostgresRelationshipRecord(
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
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.cursor()
        cur.execute(
            """UPDATE relationships SET is_available = FALSE, created_at = %s
               WHERE source_id = %s AND target_id = %s
               AND relationship_type = %s AND is_available = TRUE""",
            (now, source_id, target_id, relationship_type),
        )
        return cur.rowcount > 0

    def find_by_source(
        self, source_id: str, relationship_type: Optional[str] = None
    ) -> Iterator[PostgresRelationshipRecord]:
        cur = self._conn.cursor()
        sql = "SELECT * FROM relationships WHERE source_id = %s AND is_available = TRUE"
        params: list[Any] = [source_id]

        if relationship_type:
            sql += " AND relationship_type = %s"
            params.append(relationship_type)

        cur.execute(sql, params)
        for row in cur.fetchall():
            yield self._row_to_relationship(row)

    def find_by_target(
        self, target_id: str, relationship_type: Optional[str] = None
    ) -> Iterator[PostgresRelationshipRecord]:
        cur = self._conn.cursor()
        sql = "SELECT * FROM relationships WHERE target_id = %s AND is_available = TRUE"
        params: list[Any] = [target_id]

        if relationship_type:
            sql += " AND relationship_type = %s"
            params.append(relationship_type)

        cur.execute(sql, params)
        for row in cur.fetchall():
            yield self._row_to_relationship(row)

    def find(
        self,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        relationship_type: Optional[str] = None,
    ) -> Iterator[PostgresRelationshipRecord]:
        cur = self._conn.cursor()
        conditions = ["is_available = TRUE"]
        params: list[Any] = []

        if source_id:
            conditions.append("source_id = %s")
            params.append(source_id)
        if target_id:
            conditions.append("target_id = %s")
            params.append(target_id)
        if relationship_type:
            conditions.append("relationship_type = %s")
            params.append(relationship_type)

        sql = f"SELECT * FROM relationships WHERE {' AND '.join(conditions)}"
        cur.execute(sql, params)
        for row in cur.fetchall():
            yield self._row_to_relationship(row)

    def traverse(
        self,
        source_id: str,
        relationship_type: Optional[str] = None,
        max_depth: int = 10,
    ) -> list[dict[str, Any]]:
        cur = self._conn.cursor()

        if relationship_type:
            cte_sql = """
                WITH RECURSIVE traversal(id, source_id, target_id, relationship_type, depth) AS (
                    SELECT id, source_id, target_id, relationship_type, 1
                    FROM relationships
                    WHERE source_id = %s AND relationship_type = %s AND is_available = TRUE
                    UNION ALL
                    SELECT r.id, r.source_id, r.target_id, r.relationship_type, t.depth + 1
                    FROM relationships r
                    INNER JOIN traversal t ON r.source_id = t.target_id
                    WHERE r.is_available = TRUE AND t.depth < %s
                )
                SELECT * FROM traversal
            """
            cur.execute(cte_sql, (source_id, relationship_type, max_depth))
        else:
            cte_sql = """
                WITH RECURSIVE traversal(id, source_id, target_id, relationship_type, depth) AS (
                    SELECT id, source_id, target_id, relationship_type, 1
                    FROM relationships
                    WHERE source_id = %s AND is_available = TRUE
                    UNION ALL
                    SELECT r.id, r.source_id, r.target_id, r.relationship_type, t.depth + 1
                    FROM relationships r
                    INNER JOIN traversal t ON r.source_id = t.target_id
                    WHERE r.is_available = TRUE AND t.depth < %s
                )
                SELECT * FROM traversal
            """
            cur.execute(cte_sql, (source_id, max_depth))

        results = []
        for row in cur.fetchall():
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

    def _row_to_relationship(self, row: dict) -> PostgresRelationshipRecord:
        return PostgresRelationshipRecord(
            id=row["id"],
            source_id=row["source_id"],
            target_id=row["target_id"],
            relationship_type=row["relationship_type"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else None,
            created_at=row["created_at"],
            created_by=row["created_by"],
            is_available=bool(row["is_available"]),
        )


class PostgresExternalIdRecord:
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


class PostgresExternalIdStore:
    """Storage adapter for managing external IDs in PostgreSQL.

    Uses atomic upserts (INSERT ... ON CONFLICT) for multi-instance safety
    as required by the design spec §2.3.
    """

    def __init__(self, conn: psycopg.Connection):
        self._conn = conn

    def create_external_id(
        self, entity_id: str, external_id: str
    ) -> PostgresExternalIdRecord:
        now = datetime.now(timezone.utc).isoformat()
        record_id = str(uuid.uuid4())

        cur = self._conn.cursor()
        cur.execute(
            """INSERT INTO entity_external_ids
               (id, entity_id, external_id, created_at, superseded_at)
               VALUES (%s, %s, %s, %s, NULL)
               ON CONFLICT (entity_id, external_id)
               WHERE superseded_at IS NULL
               DO NOTHING""",
            (record_id, entity_id, external_id, now),
        )

        return PostgresExternalIdRecord(
            id=record_id,
            entity_id=entity_id,
            external_id=external_id,
            created_at=now,
            superseded_at=None,
        )

    def get_entity_by_external_id(
        self, external_id: str, include_archived: bool = False
    ) -> Optional[PostgresExternalIdRecord]:
        cur = self._conn.cursor()

        if include_archived:
            cur.execute(
                """SELECT * FROM entity_external_ids
                   WHERE external_id = %s AND superseded_at IS NULL
                   ORDER BY created_at DESC
                   LIMIT 1""",
                (external_id,),
            )
        else:
            cur.execute(
                """SELECT eei.* FROM entity_external_ids eei
                   INNER JOIN entities e ON eei.entity_id = e.id
                   WHERE eei.external_id = %s AND e.is_available = TRUE
                   AND eei.superseded_at IS NULL
                   ORDER BY eei.created_at DESC
                   LIMIT 1""",
                (external_id,),
            )

        row = cur.fetchone()
        if row is None:
            return None

        return self._row_to_external_id(row)

    def list_external_ids_for_entity(
        self, entity_id: str, include_superseded: bool = False
    ) -> Iterator[PostgresExternalIdRecord]:
        cur = self._conn.cursor()

        if include_superseded:
            cur.execute(
                """SELECT * FROM entity_external_ids
                   WHERE entity_id = %s
                   ORDER BY created_at DESC""",
                (entity_id,),
            )
        else:
            cur.execute(
                """SELECT * FROM entity_external_ids
                   WHERE entity_id = %s AND superseded_at IS NULL
                   ORDER BY created_at DESC""",
                (entity_id,),
            )

        for row in cur.fetchall():
            yield self._row_to_external_id(row)

    def supersede_external_id(
        self, entity_id: str, old_external_id: str, new_external_id: str
    ) -> PostgresExternalIdRecord:
        now = datetime.now(timezone.utc).isoformat()
        new_record_id = str(uuid.uuid4())

        cur = self._conn.cursor()
        cur.execute(
            """UPDATE entity_external_ids
               SET superseded_at = %s
               WHERE entity_id = %s AND external_id = %s AND superseded_at IS NULL""",
            (now, entity_id, old_external_id),
        )

        cur.execute(
            """INSERT INTO entity_external_ids
               (id, entity_id, external_id, created_at, superseded_at)
               VALUES (%s, %s, %s, %s, NULL)""",
            (new_record_id, entity_id, new_external_id, now),
        )

        return PostgresExternalIdRecord(
            id=new_record_id,
            entity_id=entity_id,
            external_id=new_external_id,
            created_at=now,
            superseded_at=None,
        )

    def _row_to_external_id(self, row: dict) -> PostgresExternalIdRecord:
        return PostgresExternalIdRecord(
            id=row["id"],
            entity_id=row["entity_id"],
            external_id=row["external_id"],
            created_at=row["created_at"],
            superseded_at=row["superseded_at"],
        )


class PostgresFTSStore:
    """Full-text search store using PostgreSQL tsvector/tsquery.

    Replaces SQLite FTS5 with PostgreSQL's native full-text search:
    - tsvector/tsquery for text search
    - ts_rank for relevance ranking
    - pg_trgm extension for trigram similarity (fuzzy matching)
    """

    def __init__(self, conn: psycopg.Connection):
        self._conn = conn

    def create_fts_table(
        self,
        table_name: str,
        columns: list[str],
    ) -> None:
        """Create an FTS shadow table with tsvector column and GIN index."""
        cur = self._conn.cursor()
        cur.execute(
            f"""CREATE TABLE IF NOT EXISTS {table_name} (
                entity_id TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                content_tsvector TSVECTOR
                    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
                PRIMARY KEY (entity_id)
            )"""
        )
        cur.execute(
            f"""CREATE INDEX IF NOT EXISTS idx_{table_name}_tsvector
                ON {table_name} USING GIN (content_tsvector)"""
        )
        # Trigram index for fuzzy matching
        cur.execute(
            f"""CREATE INDEX IF NOT EXISTS idx_{table_name}_trigram
                ON {table_name} USING GIN (content gin_trgm_ops)"""
        )

    def sync_entity_to_fts(
        self,
        table_name: str,
        entity_id: str,
        content: str,
    ) -> None:
        """Upsert an entity into the FTS table."""
        cur = self._conn.cursor()
        cur.execute(
            f"""INSERT INTO {table_name} (entity_id, content)
                VALUES (%s, %s)
                ON CONFLICT (entity_id) DO UPDATE SET content = EXCLUDED.content""",
            (entity_id, content),
        )

    def remove_entity_from_fts(self, table_name: str, entity_id: str) -> None:
        cur = self._conn.cursor()
        cur.execute(
            f"DELETE FROM {table_name} WHERE entity_id = %s",
            (entity_id,),
        )

    def drop_fts_table(self, table_name: str) -> None:
        cur = self._conn.cursor()
        cur.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")

    def insert_fts_entry(self, table_name: str, entity_id: str, content: str) -> None:
        cur = self._conn.cursor()
        cur.execute(
            f"INSERT INTO {table_name} (entity_id, content) VALUES (%s, %s)",
            (entity_id, content),
        )

    def update_fts_entry(self, table_name: str, entity_id: str, content: str) -> None:
        cur = self._conn.cursor()
        cur.execute(
            f"UPDATE {table_name} SET content = %s WHERE entity_id = %s",
            (content, entity_id),
        )

    def delete_fts_entry(self, table_name: str, entity_id: str) -> None:
        cur = self._conn.cursor()
        cur.execute(
            f"DELETE FROM {table_name} WHERE entity_id = %s",
            (entity_id,),
        )

    def search_fts(
        self,
        table_name: str,
        query: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Search using tsquery with ts_rank scoring."""
        cur = self._conn.cursor()
        # Use plainto_tsquery for user-friendly input (no need for tsquery syntax)
        cur.execute(
            f"""SELECT entity_id, content,
                       ts_rank(content_tsvector, plainto_tsquery('english', %s)) AS rank
                FROM {table_name}
                WHERE content_tsvector @@ plainto_tsquery('english', %s)
                ORDER BY rank DESC
                LIMIT %s""",
            (query, query, limit),
        )
        return [
            {"entity_id": row["entity_id"], "content": row["content"]}
            for row in cur.fetchall()
        ]

    def search_fts_fuzzy(
        self,
        table_name: str,
        query: str,
        limit: int = 100,
        similarity_threshold: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Fuzzy search using trigram similarity (pg_trgm)."""
        cur = self._conn.cursor()
        cur.execute(
            f"""SELECT entity_id, content,
                       similarity(content, %s) AS sim_score
                FROM {table_name}
                WHERE similarity(content, %s) > %s
                ORDER BY sim_score DESC
                LIMIT %s""",
            (query, query, similarity_threshold, limit),
        )
        return [
            {
                "entity_id": row["entity_id"],
                "content": row["content"],
                "score": row["sim_score"],
            }
            for row in cur.fetchall()
        ]

    def get_fts_tables_for_entity_type(self, entity_type: str) -> list[str]:
        cur = self._conn.cursor()
        prefix = f"fts_{entity_type.lower()}_"
        cur.execute(
            """SELECT tablename FROM pg_tables
               WHERE schemaname = 'public' AND tablename LIKE %s""",
            (prefix + "%",),
        )
        return [row["tablename"] for row in cur.fetchall()]

    def fts_table_exists(self, table_name: str) -> bool:
        cur = self._conn.cursor()
        cur.execute(
            """SELECT EXISTS (
                SELECT 1 FROM pg_tables
                WHERE schemaname = 'public' AND tablename = %s
            )""",
            (table_name,),
        )
        row = cur.fetchone()
        return row["exists"] if row else False


# ---------------------------------------------------------------------------
# Trigger SQL for provenance immutability
# ---------------------------------------------------------------------------

POSTGRES_PROVENANCE_TRIGGERS = """
-- Enforce hippo_append_only on ProvenanceRecord at the SQL level
-- (sec9 §9.6 / Decision 9.6.C). A single BEFORE UPDATE / BEFORE DELETE
-- trigger covers any column change and any row deletion.
CREATE OR REPLACE FUNCTION prevent_provenance_update()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Cannot update ProvenanceRecord: hippo_append_only class';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_prevent_provenance_update ON "ProvenanceRecord";
CREATE TRIGGER trg_prevent_provenance_update
    BEFORE UPDATE ON "ProvenanceRecord"
    FOR EACH ROW
    EXECUTE FUNCTION prevent_provenance_update();

CREATE OR REPLACE FUNCTION prevent_provenance_delete()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Cannot delete ProvenanceRecord: hippo_append_only class';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_prevent_provenance_delete ON "ProvenanceRecord";
CREATE TRIGGER trg_prevent_provenance_delete
    BEFORE DELETE ON "ProvenanceRecord"
    FOR EACH ROW
    EXECUTE FUNCTION prevent_provenance_delete();
"""


class PostgresAdapter(EntityStore[PostgresEntity]):
    """PostgreSQL storage adapter with connection pooling.

    Args:
        database_url: PostgreSQL connection string (e.g. postgresql://user:pass@host:5432/db).
            Can also be set via HIPPO_DATABASE_URL environment variable.
        min_pool_size: Minimum number of connections in the pool (default: 2).
        max_pool_size: Maximum number of connections in the pool (default: 10).
    """

    def __init__(
        self,
        database_url: str,
        min_pool_size: int = 2,
        max_pool_size: int = 10,
        schema_version: Optional[str] = None,
    ):
        self.database_url = database_url
        self.min_pool_size = min_pool_size
        self.max_pool_size = max_pool_size
        self._schema_version = schema_version or ""
        self._provenance_store: Optional[PostgresProvenanceStore] = None

        try:
            self._pool = ConnectionPool(
                conninfo=database_url,
                min_size=min_pool_size,
                max_size=max_pool_size,
                kwargs={"row_factory": dict_row},
            )
        except Exception as e:
            raise AdapterError(
                message=f"Failed to create PostgreSQL connection pool: {e}",
                adapter_type="postgres",
                cause=e,
            )

        self._init_database()

    @contextmanager
    def _connection(self) -> Generator[psycopg.Connection, None, None]:
        """Get a connection from the pool."""
        try:
            with self._pool.connection() as conn:
                yield conn
        except psycopg.Error as e:
            raise AdapterError(
                message=f"PostgreSQL connection error: {e}",
                adapter_type="postgres",
                cause=e,
            )

    @contextmanager
    def _transaction(self) -> Generator[psycopg.Connection, None, None]:
        """Get a connection with explicit transaction management."""
        with self._connection() as conn:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def _init_database(self) -> None:
        """Initialize database schema and extensions."""
        with self._transaction() as conn:
            cur = conn.cursor()

            # Enable required extensions
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS hippo_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    is_available BOOLEAN NOT NULL DEFAULT TRUE,
                    version INTEGER NOT NULL DEFAULT 1,
                    data JSONB NOT NULL,
                    created_at TEXT,
                    updated_at TEXT,
                    superseded_by TEXT
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_entities_type
                ON entities(entity_type)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_entities_available
                ON entities(is_available)
            """)
            # GIN index on JSONB data for efficient field queries
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_entities_data
                ON entities USING GIN (data)
            """)

            # Drop legacy provenance table if it exists; data migration
            # from legacy to ProvenanceRecord is not supported (dev-only
            # deployments per Decision 9.6.D).
            cur.execute("DROP TABLE IF EXISTS provenance CASCADE")

            # ProvenanceRecord table (sec9 §9.6 / Decision 9.6.D). Shape
            # matches what the LinkML DDL generator produces from
            # hippo_core.ProvenanceRecord (verified by
            # tests/core/test_ddl_generator.py::
            # TestHippoCoreProvenanceRecordDDL).
            cur.execute("""
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
                    is_available BOOLEAN NOT NULL DEFAULT TRUE,
                    superseded_by TEXT
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_ProvenanceRecord_entity_id
                ON "ProvenanceRecord"(entity_id)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_ProvenanceRecord_operation
                ON "ProvenanceRecord"(operation)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_ProvenanceRecord_timestamp
                ON "ProvenanceRecord"(timestamp)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_ProvenanceRecord_process_id
                ON "ProvenanceRecord"(process_id)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_ProvenanceRecord_entity_timestamp
                ON "ProvenanceRecord"(entity_id, timestamp)
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS relationships (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relationship_type TEXT NOT NULL,
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    created_by TEXT,
                    is_available BOOLEAN NOT NULL DEFAULT TRUE
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_relationships_source
                ON relationships(source_id)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_relationships_target
                ON relationships(target_id)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_relationships_type
                ON relationships(relationship_type)
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS entity_external_ids (
                    id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                    external_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    superseded_at TEXT
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_entity_external_ids_entity
                ON entity_external_ids(entity_id)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_entity_external_ids_external
                ON entity_external_ids(external_id, created_at DESC)
            """)
            # Unique partial index for atomic external ID registration
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_entity_external_ids_unique_active
                ON entity_external_ids(entity_id, external_id)
                WHERE superseded_at IS NULL
            """)

            # Provenance immutability triggers
            cur.execute(POSTGRES_PROVENANCE_TRIGGERS)

            # entity_provenance_summary view — sec9 §9.7 computed fields.
            # Reads the ProvenanceRecord table; the availability-change
            # exclusion mirrors the SOFT_DELETE logic (Decision 9.6.B):
            # availability_change with status='deleted' or is_available=false
            # does not count toward updated_at.
            cur.execute("""
                CREATE OR REPLACE VIEW entity_provenance_summary AS
                SELECT
                    p1.entity_id,
                    p1.entity_type,
                    MIN(p1.timestamp) AS created_at,
                    MAX(CASE
                        WHEN p1.operation = 'availability_change'
                             AND (p1.patch::jsonb->>'status' = 'deleted'
                                  OR p1.patch::jsonb->>'is_available' = 'false')
                            THEN NULL
                        ELSE p1.timestamp
                    END) AS updated_at,
                    (SELECT p2.schema_version FROM "ProvenanceRecord" p2
                     WHERE p2.entity_id = p1.entity_id
                     ORDER BY p2.timestamp DESC LIMIT 1) AS schema_version
                FROM "ProvenanceRecord" p1
                WHERE p1.entity_id IS NOT NULL
                GROUP BY p1.entity_id, p1.entity_type
            """)

    # ------------------------------------------------------------------
    # EntityStore protocol implementation
    # ------------------------------------------------------------------

    def create(
        self, entity: PostgresEntity, user_context: Optional[str] = None
    ) -> PostgresEntity:
        """Create a new entity using atomic upsert for multi-instance safety."""
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
            cur = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()
            created_at = getattr(entity, "created_at", None) or now
            updated_at = getattr(entity, "updated_at", None) or now

            # Atomic upsert per design spec §2.3
            cur.execute(
                """INSERT INTO entities
                   (id, entity_type, is_available, version, data, created_at, updated_at)
                   VALUES (%s, %s, TRUE, %s, %s, %s, %s)
                   ON CONFLICT (id) DO UPDATE SET
                       data = EXCLUDED.data,
                       updated_at = EXCLUDED.updated_at,
                       version = entities.version + 1""",
                (
                    entity_id,
                    entity_type,
                    entity.version if hasattr(entity, "version") else 1,
                    json.dumps(entity_data),
                    created_at,
                    updated_at,
                ),
            )

            provenance = PostgresProvenanceStore(conn, self._schema_version)
            provenance.record(
                entity_id=entity_id,
                entity_type=entity_type,
                operation="create",
                actor_id=user_context,
                patch=entity_data,
            )

        return entity

    def read(self, entity_id: str) -> Optional[PostgresEntity]:
        """Read an entity by its ID (available entities only)."""
        with self._transaction() as conn:
            cur = conn.cursor()
            cur.execute(
                """SELECT id, entity_type, is_available, version, data,
                          created_at, updated_at, superseded_by
                   FROM entities WHERE id = %s AND is_available = TRUE""",
                (entity_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None

            return self._row_to_entity(row)

    def read_any(self, entity_id: str) -> Optional[PostgresEntity]:
        """Read an entity by its ID, regardless of availability."""
        with self._transaction() as conn:
            cur = conn.cursor()
            cur.execute(
                """SELECT id, entity_type, is_available, version, data,
                          created_at, updated_at, superseded_by
                   FROM entities WHERE id = %s""",
                (entity_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None

            return self._row_to_entity(row)

    def resolve_type(self, entity_id: str) -> Optional[str]:
        """Return the entity_type for a given UUID, or None if unknown.

        Per sec9 §9.5's identity model — UUID → type resolution. Uses the
        existing `entities` table's type discriminator.
        """
        with self._transaction() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT entity_type FROM entities WHERE id = %s",
                (entity_id,),
            )
            row = cur.fetchone()
            return row["entity_type"] if row else None

    def resolve_types(self, entity_ids: list[str]) -> dict[str, str]:
        """Batch variant of ``resolve_type``. Returns a dict keyed by id.

        Unknown UUIDs are absent from the returned dict. One SQL round-trip
        regardless of input size.
        """
        if not entity_ids:
            return {}
        with self._transaction() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, entity_type FROM entities WHERE id = ANY(%s)",
                (list(entity_ids),),
            )
            return {row["id"]: row["entity_type"] for row in cur.fetchall()}

    def update(self, entity: PostgresEntity) -> PostgresEntity:
        """Update an existing entity."""
        with self._transaction() as conn:
            cur = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()
            cur.execute(
                """UPDATE entities SET updated_at = %s
                   WHERE id = %s AND is_available = TRUE""",
                (now, entity.id),
            )

        return entity

    def delete(self, entity_id: str, user_context: Optional[str] = None) -> bool:
        """Delete an entity by its ID (soft delete)."""
        with self._transaction() as conn:
            cur = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()

            cur.execute(
                "SELECT id, entity_type, data FROM entities WHERE id = %s AND is_available = TRUE",
                (entity_id,),
            )
            row = cur.fetchone()
            if row is None:
                return False

            entity_type = row["entity_type"]
            original_data = row["data"] if isinstance(row["data"], dict) else json.loads(row["data"])

            cur.execute(
                """UPDATE entities SET is_available = FALSE, updated_at = %s
                   WHERE id = %s AND is_available = TRUE""",
                (now, entity_id),
            )

            provenance = PostgresProvenanceStore(conn, self._schema_version)
            provenance.record(
                entity_id=entity_id,
                entity_type=entity_type,
                operation="availability_change",
                actor_id=user_context,
                patch={"status": "deleted", "is_available": False, "data": original_data},
            )

            return True

    def find(self, query: Query) -> Iterator[PostgresEntity]:
        """Find entities matching a query."""
        with self._transaction() as conn:
            cur = conn.cursor()

            sql = """SELECT id, entity_type, is_available, version, data,
                            created_at, updated_at, superseded_by
                     FROM entities WHERE is_available = TRUE"""
            params: list[Any] = []

            if query.entity_type:
                sql += " AND entity_type = %s"
                params.append(query.entity_type)

            if query.filters:
                joiner = " OR " if getattr(query, "filter_mode", "and") == "or" else " AND "
                filter_clauses = []
                for f in query.filters:
                    if "field" in f and "value" in f:
                        field = f["field"]
                        value = f["value"]
                        filter_clauses.append("data->>%s = %s")
                        params.append(field)
                        params.append(str(value))
                    else:
                        for key, value in f.items():
                            filter_clauses.append("data->>%s = %s")
                            params.append(key)
                            params.append(str(value))
                if filter_clauses:
                    sql += " AND (" + joiner.join(filter_clauses) + ")"

            if query.limit:
                sql += " LIMIT %s"
                params.append(query.limit)
                if query.offset:
                    sql += " OFFSET %s"
                    params.append(query.offset)
            elif query.offset:
                sql += " OFFSET %s"
                params.append(query.offset)

            cur.execute(sql, params)
            for row in cur.fetchall():
                yield self._row_to_entity(row)

    def findAll(self) -> Iterator[PostgresEntity]:
        """Find all entities."""
        return self.find(Query())

    def findBy(self, **kwargs: Any) -> Iterator[PostgresEntity]:
        """Find entities by field values."""
        query = Query()
        query.filters = [kwargs]
        return self.find(query)

    def search(
        self,
        query: str,
        entity_type: str,
        field_name: str,
        min_score: float = 0.0,
        limit: int = 100,
    ) -> list[ScoredMatch]:
        """Search entities using PostgreSQL full-text search with ts_rank.

        Uses tsvector/tsquery for text search with relevance ranking.
        Falls back to trigram similarity for fuzzy matching when tsquery
        returns no results.
        """
        if limit <= 0:
            limit = 100
        limit = min(limit, 1000)

        fts_table_name = f"fts_{entity_type.lower()}_{field_name.lower()}"

        with self._transaction() as conn:
            cur = conn.cursor()

            # Check FTS table exists
            cur.execute(
                """SELECT EXISTS (
                    SELECT 1 FROM pg_tables
                    WHERE schemaname = 'public' AND tablename = %s
                )""",
                (fts_table_name,),
            )
            if not cur.fetchone()["exists"]:
                raise SearchCapabilityError(
                    message=f"Field '{field_name}' on entity type '{entity_type}' is not FTS-indexed",
                    field_name=field_name,
                    entity_type=entity_type,
                )

            # Full-text search with ts_rank
            cur.execute(
                f"""SELECT fts.entity_id,
                           ts_rank(fts.content_tsvector, plainto_tsquery('english', %s)) AS rank_score
                    FROM {fts_table_name} fts
                    INNER JOIN entities e ON fts.entity_id = e.id
                    WHERE fts.content_tsvector @@ plainto_tsquery('english', %s)
                    AND e.entity_type = %s
                    AND e.is_available = TRUE
                    ORDER BY rank_score DESC
                    LIMIT %s""",
                (query, query, entity_type, limit * 2),
            )

            rows = cur.fetchall()

            # If no tsquery results, fall back to trigram similarity
            if not rows:
                cur.execute(
                    f"""SELECT fts.entity_id,
                               similarity(fts.content, %s) AS rank_score
                        FROM {fts_table_name} fts
                        INNER JOIN entities e ON fts.entity_id = e.id
                        WHERE similarity(fts.content, %s) > 0.1
                        AND e.entity_type = %s
                        AND e.is_available = TRUE
                        ORDER BY rank_score DESC
                        LIMIT %s""",
                    (query, query, entity_type, limit * 2),
                )
                rows = cur.fetchall()

            results = []
            max_score = None
            for row in rows:
                if max_score is None:
                    max_score = row["rank_score"] if row["rank_score"] > 0 else 1.0

                normalized = row["rank_score"] / max_score if max_score > 0 else 0.0

                if normalized >= min_score:
                    results.append(
                        ScoredMatch(
                            entity_id=row["entity_id"],
                            score=normalized,
                            highlights=None,
                        )
                    )

            results.sort(key=lambda x: x.score, reverse=True)
            return results[:limit]

    # ------------------------------------------------------------------
    # FTS management
    # ------------------------------------------------------------------

    def create_fts_table(
        self,
        table_name: str,
        columns: list[str],
        content_table: str = "entities",
    ) -> None:
        with self._transaction() as conn:
            fts = PostgresFTSStore(conn)
            fts.create_fts_table(table_name, columns)

    def search_fts(
        self,
        table_name: str,
        query: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        with self._transaction() as conn:
            fts = PostgresFTSStore(conn)
            return fts.search_fts(table_name, query, limit)

    def get_fts_tables_for_entity_type(self, entity_type: str) -> list[str]:
        with self._transaction() as conn:
            fts = PostgresFTSStore(conn)
            return fts.get_fts_tables_for_entity_type(entity_type)

    # ------------------------------------------------------------------
    # Provenance / tracking
    # ------------------------------------------------------------------

    def track_creation(
        self, entity: PostgresEntity, metadata: Dict[str, Any]
    ) -> ProvenanceRecordType:
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
        self, entity: PostgresEntity, metadata: Dict[str, Any]
    ) -> ProvenanceRecordType:
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
        return ProvenanceRecordType(
            timestamp=datetime.now(timezone.utc),
            operation="availability_change",
            entity_type="unknown",
            entity_id=entity_id,
            actor_id="",
            schema_version="",
            patch={"status": "deleted", **metadata},
        )

    def search_capabilities(self) -> set[str]:
        """PostgreSQL adapter supports FTS and trigram fuzzy search."""
        return {"fts", "trigram"}

    # ------------------------------------------------------------------
    # Temporal queries
    # ------------------------------------------------------------------

    def history(self, entity_id: str) -> list[dict[str, Any]]:
        with self._transaction() as conn:
            provenance = PostgresProvenanceStore(conn, self._schema_version)
            return provenance.get_history(entity_id)

    def get_temporal(
        self, entity_ids: list[str]
    ) -> "dict[str, TemporalRecord]":
        """Batch sec9 §9.7 temporal-field derivation. One SQL round-trip."""
        with self._transaction() as conn:
            provenance = PostgresProvenanceStore(conn, self._schema_version)
            return provenance.get_temporal(entity_ids)

    def state_at(self, entity_id: str, timestamp: str) -> Optional[dict[str, Any]]:
        with self._transaction() as conn:
            provenance = PostgresProvenanceStore(conn, self._schema_version)

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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _row_to_entity(self, row: dict) -> PostgresEntity:
        data = row["data"]
        if isinstance(data, str):
            data = json.loads(data)

        return PostgresEntity(
            id=row["id"],
            entity_type=row["entity_type"],
            is_available=bool(row["is_available"]),
            version=row["version"],
            data=data if data else {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            superseded_by=row.get("superseded_by"),
        )

    def _get_provenance_store(
        self, conn: psycopg.Connection
    ) -> PostgresProvenanceStore:
        return PostgresProvenanceStore(conn, self._schema_version)

    def _get_relationship_store(
        self, conn: psycopg.Connection
    ) -> PostgresRelationshipStore:
        return PostgresRelationshipStore(conn)

    def _get_external_id_store(
        self, conn: psycopg.Connection
    ) -> PostgresExternalIdStore:
        return PostgresExternalIdStore(conn)

    def _get_fts_store(self, conn: psycopg.Connection) -> PostgresFTSStore:
        return PostgresFTSStore(conn)

    def close(self) -> None:
        """Close the connection pool."""
        if hasattr(self, "_pool") and self._pool:
            self._pool.close()
