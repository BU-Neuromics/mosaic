"""Relationship management for Hippo entities."""

from datetime import datetime, timezone
from typing import Any, Iterator, Optional

from hippo.core.exceptions import EntityNotFoundError, HippoError
from hippo.core.storage.adapters.sqlite_adapter import (
    RelationshipStore,
    SQLiteAdapter,
)


class RelationshipExistsError(HippoError):
    """Exception raised when a relationship already exists."""

    def __init__(
        self,
        message: str,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        relationship_type: Optional[str] = None,
        **context: Any,
    ):
        self.source_id = source_id
        self.target_id = target_id
        self.relationship_type = relationship_type
        context["source_id"] = source_id
        context["target_id"] = target_id
        context["relationship_type"] = relationship_type
        super().__init__(message, **context)


class RelationshipNotFoundError(HippoError):
    """Exception raised when a relationship is not found."""

    def __init__(
        self,
        message: str,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        relationship_type: Optional[str] = None,
        **context: Any,
    ):
        self.source_id = source_id
        self.target_id = target_id
        self.relationship_type = relationship_type
        context["source_id"] = source_id
        context["target_id"] = target_id
        context["relationship_type"] = relationship_type
        super().__init__(message, **context)


class RelationshipManager:
    """Manager for entity relationships.

    Provides methods for creating, removing, and traversing relationships
    between entities in the Hippo Metadata Tracking Service.
    """

    def __init__(
        self,
        storage: Optional[SQLiteAdapter] = None,
        user_context: Optional[str] = None,
    ):
        """Initialize RelationshipManager.

        Args:
            storage: SQLite storage adapter. If not provided, relationships
                will be tracked in memory only.
            user_context: User identifier for audit purposes.
        """
        self._storage = storage
        self._user_context = user_context

    @property
    def storage(self) -> Optional[SQLiteAdapter]:
        """Get the storage adapter."""
        return self._storage

    def set_storage(self, storage: SQLiteAdapter) -> None:
        """Set the storage adapter."""
        self._storage = storage

    def relate(
        self,
        source_id: str,
        target_id: str,
        relationship_type: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Create a relationship between two entities.

        Args:
            source_id: The source entity ID.
            target_id: The target entity ID.
            relationship_type: The type of relationship (e.g., "contains", "belongs_to").
            metadata: Optional metadata to store with the relationship.

        Returns:
            The created relationship data.

        Raises:
            EntityNotFoundError: If source or target entity doesn't exist.
            RelationshipExistsError: If relationship already exists.
        """
        if not relationship_type or not relationship_type.strip():
            raise HippoError(
                message="Relationship type cannot be empty",
                source_id=source_id,
                target_id=target_id,
            )

        if source_id == target_id:
            raise HippoError(
                message="Cannot create self-referential relationship",
                source_id=source_id,
                target_id=target_id,
            )

        if self._storage is None:
            return {
                "source_id": source_id,
                "target_id": target_id,
                "relationship_type": relationship_type,
                "metadata": metadata,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by": self._user_context,
            }

        with self._storage._transaction() as conn:
            existing = self._storage.read(source_id)
            if existing is None:
                raise EntityNotFoundError(
                    message=f"Source entity not found: {source_id}",
                    entity_id=source_id,
                )

            existing = self._storage.read(target_id)
            if existing is None:
                raise EntityNotFoundError(
                    message=f"Target entity not found: {target_id}",
                    entity_id=target_id,
                )

            relationship_store = self._storage._get_relationship_store(conn)
            relationship = relationship_store.create(
                source_id=source_id,
                target_id=target_id,
                relationship_type=relationship_type,
                created_by=self._user_context,
                metadata=metadata,
            )

            provenance = self._storage._get_provenance_store(conn)
            provenance.record(
                entity_id=source_id,
                entity_type="relationship",
                operation_type="RELATE",
                user_context=self._user_context,
                payload={
                    "source_id": source_id,
                    "target_id": target_id,
                    "relationship_type": relationship_type,
                    "metadata": metadata,
                },
            )

            return {
                "id": relationship.id,
                "source_id": relationship.source_id,
                "target_id": relationship.target_id,
                "relationship_type": relationship.relationship_type,
                "metadata": relationship.metadata,
                "created_at": relationship.created_at,
                "created_by": relationship.created_by,
            }

    def unrelate(
        self,
        source_id: str,
        target_id: str,
        relationship_type: str,
    ) -> bool:
        """Remove a relationship between two entities.

        Args:
            source_id: The source entity ID.
            target_id: The target entity ID.
            relationship_type: The type of relationship to remove.

        Returns:
            True if the relationship was removed.

        Raises:
            RelationshipNotFoundError: If the relationship doesn't exist.
        """
        if self._storage is None:
            return True

        with self._storage._transaction() as conn:
            relationship_store = self._storage._get_relationship_store(conn)

            relationships = list(
                relationship_store.find(
                    source_id=source_id,
                    target_id=target_id,
                    relationship_type=relationship_type,
                )
            )

            if not relationships:
                raise RelationshipNotFoundError(
                    message=f"Relationship not found: {source_id} --[{relationship_type}]--> {target_id}",
                    source_id=source_id,
                    target_id=target_id,
                    relationship_type=relationship_type,
                )

            deleted = relationship_store.delete(
                source_id=source_id,
                target_id=target_id,
                relationship_type=relationship_type,
            )

            provenance = self._storage._get_provenance_store(conn)
            provenance.record(
                entity_id=source_id,
                entity_type="relationship",
                operation_type="UNRELATE",
                user_context=self._user_context,
                payload={
                    "source_id": source_id,
                    "target_id": target_id,
                    "relationship_type": relationship_type,
                },
            )

            return deleted

    def traverse(
        self,
        source_id: str,
        relationship_type: Optional[str] = None,
        max_depth: int = 10,
    ) -> list[dict[str, Any]]:
        """Traverse relationships from a starting entity.

        Args:
            source_id: The starting entity ID.
            relationship_type: Optional filter for relationship type.
            max_depth: Maximum traversal depth (default: 10).

        Returns:
            List of relationships found during traversal, with depth information.

        Raises:
            EntityNotFoundError: If the source entity doesn't exist.
        """
        if max_depth <= 0:
            max_depth = 1

        if max_depth > 100:
            max_depth = 100

        if self._storage is None:
            return []

        with self._storage._transaction() as conn:
            existing = self._storage.read(source_id)
            if existing is None:
                raise EntityNotFoundError(
                    message=f"Entity not found: {source_id}",
                    entity_id=source_id,
                )

            relationship_store = self._storage._get_relationship_store(conn)
            return relationship_store.traverse(
                source_id=source_id,
                relationship_type=relationship_type,
                max_depth=max_depth,
            )

    def find_relationships(
        self,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        relationship_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Find relationships matching criteria.

        Args:
            source_id: Optional filter by source entity ID.
            target_id: Optional filter by target entity ID.
            relationship_type: Optional filter by relationship type.

        Returns:
            List of matching relationships.
        """
        if self._storage is None:
            return []

        with self._storage._transaction() as conn:
            relationship_store = self._storage._get_relationship_store(conn)
            results = []
            for rel in relationship_store.find(
                source_id=source_id,
                target_id=target_id,
                relationship_type=relationship_type,
            ):
                results.append(
                    {
                        "id": rel.id,
                        "source_id": rel.source_id,
                        "target_id": rel.target_id,
                        "relationship_type": rel.relationship_type,
                        "metadata": rel.metadata,
                        "created_at": rel.created_at,
                        "created_by": rel.created_by,
                    }
                )
            return results
