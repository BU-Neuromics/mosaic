"""LinkMLStoreAdapter: Reserved stub for future linkml-store integration.

This adapter is a placeholder for potential future adoption of the linkml-store
backend (Option a). The implementation is deferred pending architectural review
and a decision on whether to adopt linkml-store's native storage model.

For context and rationale, see:
- GitHub Issue #2: "Evaluate linkml-store as native storage backend"
- design/sec9_spike_linkml_store.md: Spike findings and architecture trade-offs

Current status: NOT IMPLEMENTED. All methods raise NotImplementedError.
"""

from typing import Any, Dict, Iterator, List, Optional

from mosaic.core.storage import EntityStore, Query, ScoredMatch
from mosaic.core.types import ProvenanceRecord


class LinkMLStoreAdapter(EntityStore):
    """Storage adapter for linkml-store backend (Option a).

    Reserved for future implementation. This adapter would provide native
    linkml-store integration if Option a is adopted following the spike
    evaluation documented in sec9_spike_linkml_store.md.

    DO NOT instantiate or register this adapter. It exists only as a
    placeholder to reserve the adapter name and interface contract.

    See GitHub Issue #2 for implementation tracking.
    """

    def __init__(self, schema_registry: Any, **kwargs: Any) -> None:
        """Initialize the LinkMLStoreAdapter.

        Args:
            schema_registry: SchemaRegistry instance for schema introspection.
            **kwargs: Additional adapter-specific configuration.

        Raises:
            NotImplementedError: Always. This adapter is not implemented.
        """
        raise NotImplementedError(
            "Reserved for future Option a adoption - see GitHub Issue #2"
        )

    def create(self, entity: Any) -> Any:
        """Create a new entity in the store.

        Raises:
            NotImplementedError: Always. This adapter is not implemented.
        """
        raise NotImplementedError(
            "Reserved for future Option a adoption - see GitHub Issue #2"
        )

    def read(self, entity_id: str) -> Optional[Any]:
        """Read an entity by its ID.

        Raises:
            NotImplementedError: Always. This adapter is not implemented.
        """
        raise NotImplementedError(
            "Reserved for future Option a adoption - see GitHub Issue #2"
        )

    def update(self, entity: Any) -> Any:
        """Update an existing entity.

        Raises:
            NotImplementedError: Always. This adapter is not implemented.
        """
        raise NotImplementedError(
            "Reserved for future Option a adoption - see GitHub Issue #2"
        )

    def delete(self, entity_id: str) -> bool:
        """Delete an entity by its ID.

        Raises:
            NotImplementedError: Always. This adapter is not implemented.
        """
        raise NotImplementedError(
            "Reserved for future Option a adoption - see GitHub Issue #2"
        )

    def find(self, query: Query, *, as_of: Optional[str] = None) -> Iterator[Any]:
        """Find entities matching a query.

        Raises:
            NotImplementedError: Always. This adapter is not implemented.
        """
        raise NotImplementedError(
            "Reserved for future Option a adoption - see GitHub Issue #2"
        )

    def findAll(self) -> Iterator[Any]:
        """Find all entities.

        Raises:
            NotImplementedError: Always. This adapter is not implemented.
        """
        raise NotImplementedError(
            "Reserved for future Option a adoption - see GitHub Issue #2"
        )

    def findBy(self, **kwargs: Any) -> Iterator[Any]:
        """Find entities by field values.

        Raises:
            NotImplementedError: Always. This adapter is not implemented.
        """
        raise NotImplementedError(
            "Reserved for future Option a adoption - see GitHub Issue #2"
        )

    def search(
        self,
        query: str,
        entity_type: str,
        field_name: str,
        min_score: float = 0.0,
        limit: int = 100,
    ) -> List[ScoredMatch]:
        """Search entities using full-text search.

        Raises:
            NotImplementedError: Always. This adapter is not implemented.
        """
        raise NotImplementedError(
            "Reserved for future Option a adoption - see GitHub Issue #2"
        )

    def track_creation(self, entity: Any, metadata: Dict[str, Any]) -> ProvenanceRecord:
        """Track the creation of an entity.

        Raises:
            NotImplementedError: Always. This adapter is not implemented.
        """
        raise NotImplementedError(
            "Reserved for future Option a adoption - see GitHub Issue #2"
        )

    def track_update(self, entity: Any, metadata: Dict[str, Any]) -> ProvenanceRecord:
        """Track the update of an entity.

        Raises:
            NotImplementedError: Always. This adapter is not implemented.
        """
        raise NotImplementedError(
            "Reserved for future Option a adoption - see GitHub Issue #2"
        )

    def track_deletion(
        self, entity_id: str, metadata: Dict[str, Any]
    ) -> ProvenanceRecord:
        """Track the deletion of an entity.

        Raises:
            NotImplementedError: Always. This adapter is not implemented.
        """
        raise NotImplementedError(
            "Reserved for future Option a adoption - see GitHub Issue #2"
        )

    def search_capabilities(self) -> set[str]:
        """Return the set of search modes supported by this adapter.

        Raises:
            NotImplementedError: Always. This adapter is not implemented.
        """
        raise NotImplementedError(
            "Reserved for future Option a adoption - see GitHub Issue #2"
        )
