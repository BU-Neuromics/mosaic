"""ProvenanceService - Version history, audit trail, and entity supersession facade."""

import json
from datetime import datetime, timezone
from typing import Any, Optional

from hippo.core.exceptions import (
    EntityAlreadySupersededError,
    EntityNotFoundError,
)
from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter


class ProvenanceService:
    """Manages provenance history, external ID operations, and entity supersession.

    This facade owns all provenance-related logic extracted from HippoClient.
    """

    def __init__(self, storage: Optional[SQLiteAdapter] = None) -> None:
        self._storage = storage

    def get_provenance_summary_map(self, entity_type: str) -> dict[str, dict]:
        """Get a map of entity_id -> provenance timestamps for all entities of a type.

        Uses the entity_provenance_summary view for efficient batch derivation.
        """
        if self._storage is None:
            return {}

        result = {}
        try:
            with self._storage._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT entity_id, created_at, updated_at
                       FROM entity_provenance_summary
                       WHERE entity_type = ?""",
                    (entity_type,),
                )
                for row in cursor.fetchall():
                    result[row["entity_id"]] = {
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                    }
        except Exception:
            pass
        return result

    def register_external_id(self, entity_id: str, external_id: str) -> dict[str, Any]:
        """Register an external ID for an entity."""
        if self._storage is None:
            raise EntityNotFoundError(
                message=f"Entity not found: {entity_id}",
                entity_type="unknown",
                entity_id=entity_id,
            )

        entity = self._storage.read(entity_id)
        if entity is None:
            raise EntityNotFoundError(
                message=f"Entity not found: {entity_id}",
                entity_type="unknown",
                entity_id=entity_id,
            )

        with self._storage._transaction() as conn:
            external_id_store = self._storage._get_external_id_store(conn)
            record = external_id_store.create_external_id(entity_id, external_id)

        return {
            "id": record.id,
            "entity_id": record.entity_id,
            "external_id": record.external_id,
            "created_at": record.created_at,
            "superseded_at": record.superseded_at,
        }

    def supersede(
        self, entity_id: str, old_external_id: str, new_external_id: str
    ) -> dict[str, Any]:
        """Supersede an entity's external ID with a new one."""
        if self._storage is None:
            raise EntityNotFoundError(
                message=f"Entity not found: {entity_id}",
                entity_type="unknown",
                entity_id=entity_id,
            )

        entity = self._storage.read(entity_id)
        if entity is None:
            raise EntityNotFoundError(
                message=f"Entity not found: {entity_id}",
                entity_type="unknown",
                entity_id=entity_id,
            )

        with self._storage._transaction() as conn:
            external_id_store = self._storage._get_external_id_store(conn)
            record = external_id_store.supersede_external_id(
                entity_id, old_external_id, new_external_id
            )

        return {
            "id": record.id,
            "entity_id": record.entity_id,
            "external_id": record.external_id,
            "created_at": record.created_at,
            "superseded_at": record.superseded_at,
        }

    def supersede_entity(
        self,
        entity_id: str,
        replacement_id: str,
        reason: Optional[str] = None,
        actor: Optional[str] = None,
    ) -> dict[str, Any]:
        """Mark an entity as superseded by a replacement entity.

        Atomic operation: marks source unavailable, writes provenance events,
        creates superseded_by relationship edge.
        """
        if self._storage is None:
            raise EntityNotFoundError(
                message=f"Entity not found: {entity_id}",
                entity_type="unknown",
                entity_id=entity_id,
            )

        read_fn = getattr(self._storage, "read_any", self._storage.read)
        source_entity = read_fn(entity_id)
        if source_entity is None:
            raise EntityNotFoundError(
                message=f"Source entity not found: {entity_id}",
                entity_type="unknown",
                entity_id=entity_id,
            )

        replacement_entity = self._storage.read(replacement_id)
        if replacement_entity is None:
            raise EntityNotFoundError(
                message=f"Replacement entity not found: {replacement_id}",
                entity_type="unknown",
                entity_id=replacement_id,
            )

        if source_entity.superseded_by is not None:
            raise EntityAlreadySupersededError(
                message=f"Entity {entity_id} is already superseded by {source_entity.superseded_by}",
                entity_id=entity_id,
                superseded_by=source_entity.superseded_by,
            )

        now = datetime.now(timezone.utc).isoformat()

        # Per sec9 §9.6, supersession must be atomic: the entity-level
        # state change, both provenance entries, and the relationship
        # edge live in one transaction. The adapter's
        # ``_set_per_class_superseded_by`` helper participates in the
        # caller-owned cursor; the public ``mark_superseded`` wrapper is
        # reserved for standalone callers.
        with self._storage._transaction() as conn:
            cursor = conn.cursor()
            self._storage._set_per_class_superseded_by(
                cursor,
                source_entity.entity_type,
                entity_id,
                replacement_id,
                is_available=False,
            )
            cursor.execute(
                """UPDATE entities SET is_available = 0, superseded_by = ?
                   WHERE id = ?""",
                (replacement_id, entity_id),
            )

            prov_store = self._storage._get_provenance_store(conn)
            prov_patch: dict[str, Any] = {}
            if reason is not None:
                prov_patch["reason"] = reason
            prov_store.record(
                entity_id=entity_id,
                entity_type=source_entity.entity_type,
                operation="supersede",
                actor_id=actor,
                derived_from_id=replacement_id,
                patch=prov_patch or None,
            )

            rel_store = self._storage._get_relationship_store(conn)
            rel_store.create(
                source_id=entity_id,
                target_id=replacement_id,
                relationship_type="superseded_by",
                created_by=actor,
                metadata={"reason": reason} if reason else None,
            )

            prov_store.record(
                entity_id=replacement_id,
                entity_type=replacement_entity.entity_type,
                operation="update",
                actor_id=actor,
                patch={
                    "note": f"Now the active replacement for superseded entity {entity_id}",
                    "supersedes": entity_id,
                },
            )

        return {
            "entity_id": entity_id,
            "replacement_id": replacement_id,
            "superseded_at": now,
            "reason": reason,
        }

    def get_by_external_id(
        self, external_id: str, include_archived: bool = False
    ) -> dict[str, Any]:
        """Get an entity by its external ID."""
        if self._storage is None:
            raise EntityNotFoundError(
                message=f"No entity found with external ID: {external_id}",
                entity_type="unknown",
                entity_id="unknown",
            )

        with self._storage._transaction() as conn:
            external_id_store = self._storage._get_external_id_store(conn)
            record = external_id_store.get_entity_by_external_id(
                external_id, include_archived=include_archived
            )

        if record is None:
            raise EntityNotFoundError(
                message=f"No entity found with external ID: {external_id}",
                entity_type="unknown",
                entity_id="unknown",
            )

        if include_archived:
            cursor = self._storage._get_connection().cursor()
            cursor.execute(
                "SELECT id, entity_type, is_available, version, data, superseded_by FROM entities WHERE id = ?",
                (record.entity_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise EntityNotFoundError(
                    message=f"Entity not found: {record.entity_id}",
                    entity_type="unknown",
                    entity_id=record.entity_id,
                )

            entity_data = json.loads(row["data"]) if row["data"] else {}
            try:
                superseded_by_val = row["superseded_by"]
            except (IndexError, KeyError):
                superseded_by_val = None
            entity = type(
                "Entity",
                (),
                {
                    "id": row["id"],
                    "entity_type": row["entity_type"],
                    "is_available": bool(row["is_available"]),
                    "version": row["version"],
                    "data": entity_data,
                    "superseded_by": superseded_by_val,
                },
            )()
        else:
            entity = self._storage.read(record.entity_id)
            if entity is None:
                raise EntityNotFoundError(
                    message=f"Entity not found: {record.entity_id}",
                    entity_type="unknown",
                    entity_id=record.entity_id,
                )

        temporal_map = self._storage.get_temporal([entity.id])
        temporal = temporal_map.get(entity.id)
        return {
            "id": entity.id,
            "entity_type": entity.entity_type,
            "data": entity.data,
            "version": entity.version,
            "created_at": temporal.created_at if temporal else None,
            "updated_at": temporal.updated_at if temporal else None,
            "external_id": record.external_id,
            "external_id_created_at": record.created_at,
        }

    def list_external_ids(
        self, entity_id: str, include_superseded: bool = False
    ) -> list[dict[str, Any]]:
        """List all external IDs for an entity."""
        if self._storage is None:
            raise EntityNotFoundError(
                message=f"Entity not found: {entity_id}",
                entity_type="unknown",
                entity_id=entity_id,
            )

        entity = self._storage.read(entity_id)
        if entity is None:
            raise EntityNotFoundError(
                message=f"Entity not found: {entity_id}",
                entity_type="unknown",
                entity_id=entity_id,
            )

        with self._storage._transaction() as conn:
            external_id_store = self._storage._get_external_id_store(conn)
            records = list(
                external_id_store.list_external_ids_for_entity(
                    entity_id, include_superseded=include_superseded
                )
            )

        return [
            {
                "id": r.id,
                "entity_id": r.entity_id,
                "external_id": r.external_id,
                "created_at": r.created_at,
                "superseded_at": r.superseded_at,
            }
            for r in records
        ]

    def history(self, entity_id: str) -> list[dict[str, Any]]:
        """Get the change history for an entity."""
        if self._storage is None:
            raise EntityNotFoundError(
                message=f"Entity not found: {entity_id}",
                entity_type="unknown",
                entity_id=entity_id,
            )

        read_fn = getattr(self._storage, "read_any", self._storage.read)
        entity = read_fn(entity_id)
        if entity is None:
            raise EntityNotFoundError(
                message=f"Entity not found: {entity_id}",
                entity_type="unknown",
                entity_id=entity_id,
            )

        return self._storage.history(entity_id)

    def state_at(self, entity_id: str, timestamp: str) -> Optional[dict[str, Any]]:
        """Get the entity state at a specific point in time."""
        if self._storage is None:
            raise EntityNotFoundError(
                message=f"Entity not found: {entity_id}",
                entity_type="unknown",
                entity_id=entity_id,
            )

        entity = self._storage.read(entity_id)
        if entity is None:
            raise EntityNotFoundError(
                message=f"Entity not found: {entity_id}",
                entity_type="unknown",
                entity_id=entity_id,
            )

        return self._storage.state_at(entity_id, timestamp)
