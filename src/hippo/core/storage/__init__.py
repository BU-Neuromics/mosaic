"""EntityStore abstract base class for storage adapters."""

from abc import ABC, abstractmethod
from typing import (
    Any,
    Dict,
    Generic,
    Iterator,
    List,
    Optional,
    Protocol,
    TypeVar,
    runtime_checkable,
)
from collections import namedtuple

from hippo.core.types import ProvenanceRecord


ScoredMatch = namedtuple("ScoredMatch", ["entity_id", "score", "highlights"])


class Entity(Protocol):
    """Protocol defining the interface for entities stored in EntityStore."""

    @property
    def id(self) -> str:
        """Return the unique identifier for this entity."""
        ...


T = TypeVar("T", bound=Entity)


class Query:
    """Query object for searching entities."""

    def __init__(
        self,
        entity_type: Optional[str] = None,
        filters: Optional[list[dict[str, Any]]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ):
        self.entity_type = entity_type
        self.filters = filters or []
        self.limit = limit
        self.offset = offset


class EntityStore(ABC, Generic[T]):
    """Abstract base class for storage adapters.

    This ABC defines the interface for all storage adapters (SQLite, PostgreSQL, etc.)
    that need to implement CRUD operations, search functionality, and provenance tracking.

    Subclasses must implement all abstract methods.
    """

    @abstractmethod
    def create(self, entity: T) -> T:
        """Create a new entity in the store.

        Args:
            entity: The entity to create. Must have an id property.

        Returns:
            The created entity with any generated fields populated.
        """
        ...

    @abstractmethod
    def read(self, entity_id: str) -> Optional[T]:
        """Read an entity by its ID.

        Args:
            entity_id: The unique identifier of the entity.

        Returns:
            The entity if found, None otherwise.
        """
        ...

    @abstractmethod
    def update(self, entity: T) -> T:
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
    def find(self, query: Query) -> Iterator[T]:
        """Find entities matching a query.

        Args:
            query: The query object containing filters and pagination.

        Returns:
            An iterator of matching entities.
        """
        ...

    @abstractmethod
    def findAll(self) -> Iterator[T]:
        """Find all entities.

        Returns:
            An iterator of all entities in the store.
        """
        ...

    @abstractmethod
    def findBy(self, **kwargs: Any) -> Iterator[T]:
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
    def track_creation(self, entity: T, metadata: Dict[str, Any]) -> ProvenanceRecord:
        """Track the creation of an entity.

        Args:
            entity: The entity that was created.
            metadata: Additional metadata about the creation.

        Returns:
            A ProvenanceRecord documenting the creation.
        """
        ...

    @abstractmethod
    def track_update(self, entity: T, metadata: Dict[str, Any]) -> ProvenanceRecord:
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


from hippo.core.storage.validating_store import ValidatingEntityStore

__all__ = [
    "Entity",
    "Query",
    "EntityStore",
    "ScoredMatch",
    "ValidatingEntityStore",
]
