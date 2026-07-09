"""EntityStore abstract base class for storage adapters."""

from abc import ABC, abstractmethod
from typing import (
    Any,
    Dict,
    Iterator,
    List,
    Optional,
    Protocol,
)
from collections import namedtuple

from mosaic.core.types import ProvenanceRecord


ScoredMatch = namedtuple("ScoredMatch", ["entity_id", "score", "highlights"])


class Entity(Protocol):
    """Protocol defining the interface for entities stored in EntityStore."""

    @property
    def id(self) -> str:
        """Return the unique identifier for this entity."""
        ...


class Query:
    """Query object for searching entities."""

    def __init__(
        self,
        entity_type: Optional[str] = None,
        filters: Optional[list[dict[str, Any]]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        filter_mode: str = "and",
    ):
        self.entity_type = entity_type
        self.filters = filters or []
        self.limit = limit
        self.offset = offset
        self.filter_mode = filter_mode  # "and" or "or"


class EntityStore(ABC):
    """Abstract base class for storage adapters.

    This ABC defines the interface for all storage adapters (SQLite, PostgreSQL, etc.)
    that need to implement CRUD operations, search functionality, and provenance tracking.

    All adapters must accept a ``schema_registry: SchemaRegistry`` parameter in their
    ``__init__`` method. This registry provides schema introspection and validation
    capabilities required for LinkML-native storage operations.

    Subclasses must implement all abstract methods.
    """

    @abstractmethod
    def create(self, entity: Any) -> Any:
        """Create a new entity in the store.

        Args:
            entity: The entity to create. Must have an id property.

        Returns:
            The created entity with any generated fields populated.
        """
        ...

    @abstractmethod
    def read(self, entity_id: str) -> Optional[Any]:
        """Read an entity by its ID.

        Args:
            entity_id: The unique identifier of the entity.

        Returns:
            The entity if found, None otherwise.
        """
        ...

    @abstractmethod
    def update(self, entity: Any) -> Any:
        """Update an existing entity.

        Args:
            entity: The entity to update. Must have an id property.

        Returns:
            The updated entity.
        """
        ...

    @abstractmethod
    def delete(self, entity_id: str) -> bool:
        """Delete an entity by its ID.

        Args:
            entity_id: The unique identifier of the entity.

        Returns:
            True if the entity was deleted, False if it wasn't found.
        """
        ...

    @abstractmethod
    def find(self, query: Query, *, as_of: Optional[str] = None) -> Iterator[Any]:
        """Find entities matching a query.

        Args:
            query: The query object containing filters and pagination.
            as_of: Optional ISO-8601 transaction-time. Reserved for as-of
                entity-set reconstruction (sec6 §6.8 / ADR-0001). Adapters that
                do not yet implement it raise ``NotImplementedError`` for a
                non-``None`` value rather than silently returning current state.

        Returns:
            An iterator of matching entities.
        """
        ...

    @abstractmethod
    def findAll(self) -> Iterator[Any]:
        """Find all entities.

        Returns:
            An iterator of all entities in the store.
        """
        ...

    @abstractmethod
    def findBy(self, **kwargs: Any) -> Iterator[Any]:
        """Find entities by field values.

        Args:
            **kwargs: Field names and values to filter by.

        Returns:
            An iterator of matching entities.
        """
        ...

    @abstractmethod
    def search(
        self,
        query: str,
        entity_type: str,
        field_name: str,
        min_score: float = 0.0,
        limit: int = 100,
    ) -> List[ScoredMatch]:
        """Search entities using full-text search.

        Args:
            query: The search query string.
            entity_type: The type of entities to search.
            field_name: The FTS-indexed field to search in.
            min_score: Minimum score threshold (0.0-1.0).
            limit: Maximum number of results to return.

        Returns:
            List of ScoredMatch objects ordered by score descending.
        """
        ...

    @abstractmethod
    def track_creation(self, entity: Any, metadata: Dict[str, Any]) -> ProvenanceRecord:
        """Track the creation of an entity.

        Args:
            entity: The entity that was created.
            metadata: Additional metadata about the creation.

        Returns:
            A ProvenanceRecord documenting the creation.
        """
        ...

    @abstractmethod
    def track_update(self, entity: Any, metadata: Dict[str, Any]) -> ProvenanceRecord:
        """Track the update of an entity.

        Args:
            entity: The entity that was updated.
            metadata: Additional metadata about the update.

        Returns:
            A ProvenanceRecord documenting the update.
        """
        ...

    @abstractmethod
    def track_deletion(
        self, entity_id: str, metadata: Dict[str, Any]
    ) -> ProvenanceRecord:
        """Track the deletion of an entity.

        Args:
            entity_id: The ID of the entity that was deleted.
            metadata: Additional metadata about the deletion.

        Returns:
            A ProvenanceRecord documenting the deletion.
        """

    @abstractmethod
    def search_capabilities(self) -> set[str]:
        """Return the set of search modes supported by this adapter.

        Returns:
            A set of supported search mode strings (e.g., {"fts", "embedding"}).
        """
        ...

    # ------------------------------------------------------------------
    # Provenance / temporal reads (sec6 §6.7–§6.8 / ADR-0001).
    #
    # Part of the EntityStore contract, but intentionally NOT @abstractmethod:
    # wrappers (ValidatingEntityStore) and adapters that do not track provenance
    # are not forced to implement them. Provenance-backed adapters (SQLite,
    # Postgres) override all three; the default raises NotImplementedError and
    # names the gap.
    # ------------------------------------------------------------------

    def history(self, entity_id: str) -> List[Dict[str, Any]]:
        """Return the full provenance history for an entity (chronological).

        See sec6 §6.7. Provenance-backed adapters override this.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement history()"
        )

    def state_at(self, entity_id: str, timestamp: str) -> Optional[Dict[str, Any]]:
        """Reconstruct an entity's state at transaction-time ``timestamp``.

        Per sec6 §6.8.2: the entity's data state is the most recent
        state-replacing (``create``/``update``) full post-image at-or-before
        ``timestamp``; availability is decided by the most recent
        ``availability_change`` at-or-before it. Returns ``None`` if the entity
        did not exist or was unavailable then. Provenance-backed adapters
        override this.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement state_at()"
        )

    def get_temporal(
        self, entity_ids: List[str], *, as_of: Optional[str] = None
    ) -> Dict[str, Any]:
        """Batch-derive computed temporal fields (sec9 §9.7) for ``entity_ids``.

        Returns a dict keyed by entity id. When ``as_of`` (ISO-8601) is given,
        the derivation is bounded to ``timestamp <= as_of`` — the
        transaction-time as-of view (sec6 §6.8). Provenance-backed adapters
        override this.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement get_temporal()"
        )


from mosaic.core.storage.validating_store import ValidatingEntityStore

__all__ = [
    "Entity",
    "Query",
    "EntityStore",
    "ScoredMatch",
    "ValidatingEntityStore",
]
