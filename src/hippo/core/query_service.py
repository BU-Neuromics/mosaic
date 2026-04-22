"""QueryService - Entity queries, FTS search, and relationship traversal facade."""

from typing import Any, Optional

from hippo.core.batch_fetcher import BatchFetcher
from hippo.core.cycle_detector import validate_no_cycle
from hippo.core.exceptions import EntityNotFoundError
from hippo.core.expand_path_parser import ExpandPathParser
from hippo.core.provenance_service import ProvenanceService
from hippo.core.relationship import RelationshipManager
from hippo.core.schema_manager import SchemaManager
from hippo.core.storage import Query
from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter


class QueryService:
    """Manages entity queries, FTS search, and relationship traversal.

    This facade owns all read/query logic extracted from HippoClient.
    """

    def __init__(
        self,
        storage: Optional[SQLiteAdapter] = None,
        schema_manager: Optional[SchemaManager] = None,
        provenance_service: Optional[ProvenanceService] = None,
    ) -> None:
        self._storage = storage
        self._schema_manager = schema_manager
        self._provenance_service = provenance_service

    @property
    def relationships(self) -> RelationshipManager:
        """Get the relationship manager (lazy-initialized)."""
        if not hasattr(self, "_relationship_manager"):
            self._relationship_manager = RelationshipManager(storage=self._storage)
        return self._relationship_manager

    @relationships.setter
    def relationships(self, value: RelationshipManager) -> None:
        self._relationship_manager = value

    def get(
        self,
        entity_type: str,
        entity_id: str,
        expand: Optional[str] = None,
        include_unavailable: bool = False,
    ) -> dict[str, Any]:
        """Get an entity by its ID."""
        if self._storage is None:
            raise EntityNotFoundError(
                message=f"Entity not found: {entity_id}",
                entity_type=entity_type,
                entity_id=entity_id,
            )

        if include_unavailable and hasattr(self._storage, "read_any"):
            entity = self._storage.read_any(entity_id)
        else:
            entity = self._storage.read(entity_id)
            if entity is None and hasattr(self._storage, "read_any"):
                any_entity = self._storage.read_any(entity_id)
                if any_entity is not None and any_entity.entity_type == entity_type:
                    raise EntityNotFoundError(
                        message=f"Entity not found: {entity_id}",
                        entity_type=entity_type,
                        entity_id=entity_id,
                    )

        if entity is None or entity.entity_type != entity_type:
            raise EntityNotFoundError(
                message=f"Entity not found: {entity_id}",
                entity_type=entity_type,
                entity_id=entity_id,
            )

        # sec9 §9.7: temporal fields computed from ProvenanceRecord at
        # read time. One SQL round-trip via get_temporal. Missing or
        # inconsistent provenance is loud per sec9 §9.2 (Provenance
        # integrity is transactional and loud).
        created_at = entity.created_at
        updated_at = entity.updated_at
        schema_version: Optional[str] = None
        created_by: Optional[str] = None
        updated_by: Optional[str] = None
        if hasattr(self._storage, "get_temporal"):
            temporal_map = self._storage.get_temporal([entity_id])
            temporal = temporal_map.get(entity_id)
            if temporal is None:
                from hippo.core.exceptions import ProvenanceIntegrityError

                raise ProvenanceIntegrityError(
                    message=(
                        f"Entity {entity_id!r} exists but has no "
                        f"ProvenanceRecord. Every mutation must emit a "
                        f"record transactionally (sec9 §9.6); missing "
                        f"provenance indicates adapter or data corruption."
                    ),
                    entity_id=entity_id,
                    inconsistency="missing_provenance",
                )
            if temporal.created_at is None:
                from hippo.core.exceptions import ProvenanceIntegrityError

                raise ProvenanceIntegrityError(
                    message=(
                        f"Entity {entity_id!r} has ProvenanceRecord entries "
                        f"but none with operation='create'. The earliest "
                        f"record for every entity MUST be a 'create' per "
                        f"sec9 §9.7."
                    ),
                    entity_id=entity_id,
                    inconsistency="missing_create_record",
                )
            created_at = temporal.created_at
            updated_at = temporal.updated_at or updated_at
            schema_version = temporal.schema_version
            created_by = temporal.created_by
            updated_by = temporal.updated_by

        result = {
            "id": entity.id,
            "entity_type": entity.entity_type,
            "data": entity.data,
            "version": entity.version,
            "created_at": created_at,
            "updated_at": updated_at,
            "schema_version": schema_version,
            "created_by": created_by,
            "updated_by": updated_by,
            "superseded_by": entity.superseded_by,
        }

        if expand:
            parsed = self._parse_and_validate_expand(expand)
            fetcher = BatchFetcher(storage=self._storage)
            fetch_result = fetcher.fetch(parsed, entity_id)
            result["_expanded"] = fetch_result.expanded_data

        return result

    def _parse_and_validate_expand(self, expand: str) -> Any:
        """Parse and validate an expand path."""
        parser = ExpandPathParser()
        parsed = parser.parse(expand)
        validate_no_cycle(parsed)
        return parsed

    def query(
        self,
        entity_type: str,
        filters: Optional[list[dict[str, Any]]] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        filter_mode: str = "and",
    ) -> "PaginatedResult":
        """Query entities with filter criteria.

        Args:
            filter_mode: How to combine filters — "and" (all must match,
                default) or "or" (any may match).
        """
        from hippo.core.types import PaginatedResult

        if self._storage is None:
            return PaginatedResult(
                items=[],
                total=0,
                limit=limit or 0,
                offset=offset or 0,
            )

        query = Query(
            entity_type=entity_type,
            filters=filters or [],
            filter_mode=filter_mode,
        )

        all_results = list(self._storage.find(query))

        # sec9 §9.7: one batch aggregation round-trip for the result set,
        # not N+1. The adapter's get_temporal returns TemporalRecord
        # dicts keyed by entity_id. Loud failure on missing provenance
        # mirrors client.get() — a corrupt entity in a page poisons the
        # page rather than silently returning stale stored columns
        # (Decision 9.7.A).
        entity_ids = [entity.id for entity in all_results]
        temporal_map: dict[str, Any] = {}
        if entity_ids and hasattr(self._storage, "get_temporal"):
            temporal_map = self._storage.get_temporal(entity_ids)

        filtered = []
        for entity in all_results:
            temporal = temporal_map.get(entity.id)
            if temporal is None and entity_ids:
                from hippo.core.exceptions import ProvenanceIntegrityError

                raise ProvenanceIntegrityError(
                    message=(
                        f"Entity {entity.id!r} exists in query results but "
                        f"has no ProvenanceRecord. sec9 §9.2 requires "
                        f"transactional provenance on every mutation."
                    ),
                    entity_id=entity.id,
                    inconsistency="missing_provenance",
                )
            if temporal is not None and temporal.created_at is None:
                from hippo.core.exceptions import ProvenanceIntegrityError

                raise ProvenanceIntegrityError(
                    message=(
                        f"Entity {entity.id!r} has ProvenanceRecord entries "
                        f"but none with operation='create'."
                    ),
                    entity_id=entity.id,
                    inconsistency="missing_create_record",
                )
            if temporal is not None:
                created_at = temporal.created_at
                updated_at = temporal.updated_at or entity.updated_at
                schema_version = temporal.schema_version
                created_by = temporal.created_by
                updated_by = temporal.updated_by
            else:
                # hasattr(storage, 'get_temporal') was False — adapter
                # predates sec9 §9.7 and can't compute. Fall back to
                # stored columns. Non-relational adapter stub.
                created_at = entity.created_at
                updated_at = entity.updated_at
                schema_version = None
                created_by = None
                updated_by = None

            if date_from and created_at and created_at < date_from:
                continue
            if date_to and created_at and created_at > date_to:
                continue

            filtered.append(
                {
                    "id": entity.id,
                    "entity_type": entity.entity_type,
                    "data": entity.data,
                    "version": entity.version,
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "schema_version": schema_version,
                    "created_by": created_by,
                    "updated_by": updated_by,
                    "superseded_by": entity.superseded_by,
                }
            )

        filtered.sort(key=lambda x: x["created_at"] or "")

        total = len(filtered)

        actual_offset = offset or 0
        if actual_offset:
            filtered = filtered[actual_offset:]
        if limit:
            filtered = filtered[:limit]

        return PaginatedResult(
            items=filtered,
            total=total,
            limit=limit or 0,
            offset=actual_offset,
        )

    def search(
        self,
        entity_type: str,
        query: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Search entities using full-text search."""
        if self._storage is None:
            return []

        if self._schema_manager is None:
            return []

        fts_tables = self._schema_manager.get_fts_tables_for_entity_type(entity_type)
        if not fts_tables:
            return []

        results = []
        for fts_meta in fts_tables:
            fts_results = self._storage.search_fts(
                table_name=fts_meta.table_name,
                query=query,
                limit=limit,
            )
            for fts_result in fts_results:
                entity_id = fts_result["entity_id"]
                try:
                    entity = self.get(entity_type, entity_id)
                    results.append(entity)
                except EntityNotFoundError:
                    pass

        return results[:limit]
