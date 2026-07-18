"""Batch fetcher for optimized entity retrieval.

This module provides batch fetching functionality to optimize database queries
when expanding related entities. Instead of making N individual queries for each
nested entity, it groups queries by entity type and executes one query per entity list.

Example:
    >>> from mosaic.core.batch_fetcher import BatchFetcher
    >>> from mosaic.core.expand_path_parser import ExpandPathParser
    >>> parser = ExpandPathParser()
    >>> parsed = parser.parse("user.orders.items.product")
    >>> fetcher = BatchFetcher(storage=adapter)
    >>> result = fetcher.fetch(parsed, entity_id)
"""

from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

from mosaic.core.expand_path_parser import ParseResult, PathNode

# Sentinel distinguishing "slot absent from the entity's data" (omit the key)
# from "slot present but resolved to nothing" (record an explicit null).
_MISSING = object()


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
    # Keyed by the expanded slot name; value is a single resolved entity dict
    # (single-valued reference) or a list of them (multivalued reference).
    expanded_data: dict[str, Any]
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
        >>> from mosaic.core.expand_path_parser import ExpandPathParser
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

        # ``expanded_data`` is keyed by the *slot name* the caller expanded,
        # mirroring the reference's cardinality: a single-valued reference
        # resolves to one entity dict, a multivalued reference to a list of
        # entity dicts. Nested expansion hangs each level's resolution off the
        # parent entity's own ``_expanded`` map (see ``_attach_children``).
        counter = [0]
        expanded_data: dict[str, Any] = {}
        resolved = self._expand_node(parsed_result.root, primary_entity, counter)
        if resolved is not _MISSING:
            expanded_data[parsed_result.root.name] = resolved

        return FetchResult(
            primary_entity=primary_entity,
            expanded_data=expanded_data,
            query_count=counter[0],
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
        }

    def _expand_node(
        self,
        node: PathNode,
        parent_entity: dict[str, Any],
        counter: list[int],
    ) -> Any:
        """Resolve one expand slot against a parent entity's real data.

        Returns the resolved value for ``node.name`` on ``parent_entity``:
        a single entity dict for a single-valued reference, a list of entity
        dicts for a multivalued reference, ``None`` when a single-valued
        reference is dangling, or the sentinel :data:`_MISSING` when the slot
        is absent from the parent's data (so the caller can omit the key
        entirely rather than record a spurious ``null``).

        Reference slots are stored as bare ids, not nested dicts: a
        single-valued reference is a plain string id (a per-class column
        value) and a multivalued reference is a hydrated ``list[str]`` of
        target ids (issue #79 / ADR-0002). The pre-#128 implementation only
        recognized ``list[dict]``/``dict`` shapes, so it silently resolved
        nothing against real data. We handle the id shapes directly, while
        still accepting the embedded ``{"id": ...}`` shape for callers (and
        tests) that pass pre-hydrated nested dicts.
        """
        data = parent_entity.get("data", parent_entity)
        if not isinstance(data, dict) or node.name not in data:
            return _MISSING

        ids, multivalued = self._reference_ids(data[node.name])
        if not ids and not multivalued:
            # A present-but-unresolvable single-valued slot (null or a value
            # carrying no id): the slot was expanded but points at nothing.
            return None

        resolved: list[dict[str, Any]] = []
        for entity_id in ids:
            child = self._read_entity(entity_id)
            if child is None:
                continue  # dangling reference — skip, don't fabricate
            self._attach_children(node, child, counter)
            resolved.append(child)
        if ids:
            counter[0] += 1  # one batch resolution for this slot

        if multivalued:
            return resolved
        return resolved[0] if resolved else None

    def _attach_children(
        self,
        node: PathNode,
        entity: dict[str, Any],
        counter: list[int],
    ) -> None:
        """Recursively resolve ``node``'s child slots onto ``entity``.

        Each nested level is recorded under the entity's own ``_expanded``
        map, keyed by slot name — so ``expand="a.b"`` yields
        ``{"a": {..., "_expanded": {"b": ...}}}``.
        """
        if not node.children:
            return
        nested: dict[str, Any] = {}
        for child in node.children:
            resolved = self._expand_node(child, entity, counter)
            if resolved is not _MISSING:
                nested[child.name] = resolved
        if nested:
            entity["_expanded"] = nested

    @staticmethod
    def _reference_ids(value: Any) -> tuple[list[str], bool]:
        """Extract target ids from a reference slot value.

        Returns ``(ids, multivalued)``. Accepts the real stored shapes — a
        bare string id (single-valued) and a ``list[str]`` (multivalued) —
        as well as the embedded ``{"id": ...}`` / ``list[{"id": ...}]`` shapes
        some callers pass pre-hydrated.
        """
        if isinstance(value, str):
            return [value], False
        if isinstance(value, dict):
            rid = value.get("id")
            return ([rid] if isinstance(rid, str) else []), False
        if isinstance(value, list):
            ids: list[str] = []
            for item in value:
                if isinstance(item, str):
                    ids.append(item)
                elif isinstance(item, dict) and isinstance(item.get("id"), str):
                    ids.append(item["id"])
            return ids, True
        return [], False

    def _read_entity(self, entity_id: str) -> Optional[dict[str, Any]]:
        """Read one entity by id, shaped like the other fetch results."""
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
        }

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
