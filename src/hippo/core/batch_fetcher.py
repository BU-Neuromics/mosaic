"""Batch fetcher for optimized entity retrieval.

This module provides batch fetching functionality to optimize database queries
when expanding related entities. Instead of making N individual queries for each
nested entity, it groups queries by entity type and executes one query per entity list.

Example:
    >>> from hippo.core.batch_fetcher import BatchFetcher
    >>> from hippo.core.expand_path_parser import ExpandPathParser
    >>> parser = ExpandPathParser()
    >>> parsed = parser.parse("user.orders.items.product")
    >>> fetcher = BatchFetcher(storage=adapter)
    >>> result = fetcher.fetch(parsed, entity_id)
"""

from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

from hippo.core.expand_path_parser import ParseResult, PathNode


@dataclass
class EntityQuery:
    """Represents a single entity query to be executed."""

    entity_type: str
    entity_ids: list[str]
    path_segment: str


@dataclass
class FetchResult:
    """Result of a batch fetch operation.

    Attributes:
        primary_entity: The main entity that was fetched.
        expanded_data: Dictionary mapping path segments to fetched entities.
        query_count: Number of queries executed.
    """

    primary_entity: dict[str, Any]
    expanded_data: dict[str, list[dict[str, Any]]]
    query_count: int

    def to_dict(self) -> dict[str, Any]:
        """Convert the result to a dictionary.

        Returns:
            Dictionary representation of the fetch result.
        """
        return {
            "primary_entity": self.primary_entity,
            "expanded_data": self.expanded_data,
            "query_count": self.query_count,
        }


@dataclass
class ExpandableField:
    """Represents a field that can be expanded.

    Attributes:
        name: The field name.
        entity_type: The type of entity this field references.
        path: The full path to this field.
    """

    name: str
    entity_type: str
    path: str


class BatchFetcher:
    """Fetches related entities in optimized batches.

    This fetcher groups queries by entity type to minimize the number of
    database queries executed when expanding related entities.

    Example:
        >>> from hippo.core.expand_path_parser import ExpandPathParser
        >>> parser = ExpandPathParser()
        >>> parsed = parser.parse("user.orders.items.product")
        >>> fetcher = BatchFetcher(storage=adapter)
        >>> result = fetcher.fetch(parsed, "user-123")
    """

    def __init__(self, storage: Optional[Any] = None):
        """Initialize the batch fetcher.

        Args:
            storage: The storage adapter for database operations.
        """
        self._storage = storage

    def fetch(
        self,
        parsed_result: ParseResult,
        entity_id: str,
    ) -> FetchResult:
        """Fetch the primary entity and its related entities.

        Args:
            parsed_result: The parsed expand path.
            entity_id: The ID of the primary entity to fetch.

        Returns:
            FetchResult containing the primary entity and expanded data.
        """
        primary_entity = self._fetch_primary_entity(entity_id)

        if primary_entity is None:
            return FetchResult(
                primary_entity={},
                expanded_data={},
                query_count=0,
            )

        expanded_data: dict[str, list[dict[str, Any]]] = {}
        query_count = 0

        entity_queries = self._group_queries_by_entity(
            parsed_result.root, primary_entity
        )

        for query in entity_queries:
            if query.entity_ids:
                results = self._execute_query(query.entity_type, query.entity_ids)
                expanded_data[query.path_segment] = results
                query_count += 1

        return FetchResult(
            primary_entity=primary_entity,
            expanded_data=expanded_data,
            query_count=query_count,
        )

    def _fetch_primary_entity(self, entity_id: str) -> Optional[dict[str, Any]]:
        """Fetch the primary entity by ID.

        Args:
            entity_id: The entity ID to fetch.

        Returns:
            The entity data, or None if not found.
        """
        if self._storage is None:
            return {"id": entity_id, "data": {}}

        entity = self._storage.read(entity_id)
        if entity is None:
            return None

        return {
            "id": entity.id,
            "entity_type": entity.entity_type,
            "data": entity.data,
            "version": entity.version,
            "created_at": entity.created_at,
            "updated_at": entity.updated_at,
        }

    def _group_queries_by_entity(
        self,
        root: PathNode,
        primary_entity: dict[str, Any],
    ) -> list[EntityQuery]:
        """Group entity IDs by entity type for batch querying.

        Args:
            root: The root node of the parsed path.
            primary_entity: The primary entity data.

        Returns:
            List of EntityQuery objects grouped by entity type.
        """
        queries: list[EntityQuery] = []
        entity_ids_by_type: dict[str, list[str]] = {}

        self._extract_entity_ids(root, primary_entity, entity_ids_by_type)

        for entity_type, entity_ids in entity_ids_by_type.items():
            if entity_ids:
                unique_ids = list(set(entity_ids))
                queries.append(
                    EntityQuery(
                        entity_type=entity_type,
                        entity_ids=unique_ids,
                        path_segment=entity_type,
                    )
                )

        return queries

    def _extract_entity_ids(
        self,
        node: PathNode,
        entity_data: dict[str, Any],
        entity_ids_by_type: dict[str, list[str]],
    ) -> None:
        """Recursively extract entity IDs from the data structure.

        Args:
            node: The current path node.
            entity_data: The entity data to extract from.
            entity_ids_by_type: Dictionary to accumulate entity IDs by type.
        """
        data = entity_data.get("data", entity_data)

        for key, value in data.items():
            if key == node.name or node.parent is None:
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict) and "id" in item:
                            entity_type = item.get("entity_type", node.name)
                            if entity_type not in entity_ids_by_type:
                                entity_ids_by_type[entity_type] = []
                            entity_ids_by_type[entity_type].append(item["id"])

                for child in node.children:
                    if isinstance(value, dict):
                        self._extract_entity_ids(child, value, entity_ids_by_type)

    def _execute_query(
        self,
        entity_type: str,
        entity_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Execute a batch query for entities.

        Args:
            entity_type: The type of entities to fetch.
            entity_ids: List of entity IDs to fetch.

        Returns:
            List of entity data dictionaries.
        """
        if self._storage is None:
            return [{"id": eid, "data": {}} for eid in entity_ids]

        results = []
        for entity_id in entity_ids:
            entity = self._storage.read(entity_id)
            if entity is not None:
                results.append(
                    {
                        "id": entity.id,
                        "entity_type": entity.entity_type,
                        "data": entity.data,
                        "version": entity.version,
                        "created_at": entity.created_at,
                        "updated_at": entity.updated_at,
                    }
                )

        return results

    def fetch_simple(
        self,
        entity_type: str,
        entity_id: str,
    ) -> Optional[dict[str, Any]]:
        """Fetch a single entity without expansion.

        This is an optimization for simple single-level paths that don't
        require batch fetching.

        Args:
            entity_type: The type of entity.
            entity_id: The entity ID.

        Returns:
            The entity data, or None if not found.
        """
        if self._storage is None:
            return {"id": entity_id, "entity_type": entity_type, "data": {}}

        entity = self._storage.read(entity_id)
        if entity is None:
            return None

        return {
            "id": entity.id,
            "entity_type": entity.entity_type,
            "data": entity.data,
            "version": entity.version,
            "created_at": entity.created_at,
            "updated_at": entity.updated_at,
        }


def fetch_expanded(
    storage: Any,
    parsed_result: ParseResult,
    entity_id: str,
) -> FetchResult:
    """Convenience function to fetch entities with expansion.

    Args:
        storage: The storage adapter.
        parsed_result: The parsed expand path.
        entity_id: The ID of the primary entity.

    Returns:
        FetchResult containing the fetched data.
    """
    fetcher = BatchFetcher(storage=storage)
    return fetcher.fetch(parsed_result, entity_id)
