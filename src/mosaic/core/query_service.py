"""QueryService - Entity queries, FTS search, and relationship traversal facade."""

from typing import Any, Optional

from mosaic.core.batch_fetcher import BatchFetcher
from mosaic.core.cycle_detector import validate_no_cycle
from mosaic.core.exceptions import EntityNotFoundError
from mosaic.core.expand_path_parser import ExpandPathParser
from mosaic.core.provenance_service import ProvenanceService
from mosaic.core.relationship import RelationshipManager
from mosaic.core.schema_manager import SchemaManager
from mosaic.core.storage import Query, normalize_where
from mosaic.core.storage.adapters.sqlite_adapter import SQLiteAdapter


class QueryService:
    """Manages entity queries, FTS search, and relationship traversal.

    This facade owns all read/query logic extracted from MosaicClient.
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
        created_at: Optional[str] = None
        updated_at: Optional[str] = None
        schema_version: Optional[str] = None
        created_by: Optional[str] = None
        updated_by: Optional[str] = None
        if hasattr(self._storage, "get_temporal"):
            temporal_map = self._storage.get_temporal([entity_id])
            temporal = temporal_map.get(entity_id)
            if temporal is None:
                from mosaic.core.exceptions import ProvenanceIntegrityError

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
                from mosaic.core.exceptions import ProvenanceIntegrityError

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
            updated_at = temporal.updated_at
            schema_version = temporal.schema_version
            created_by = temporal.created_by
            updated_by = temporal.updated_by

        result = {
            "id": entity.id,
            "entity_type": entity.entity_type,
            "data": entity.data,
            "version": entity.version,
            "is_available": bool(entity.is_available),
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
        entity_type: Optional[str] = None,
        filters: Optional[list[dict[str, Any]]] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        filter_mode: str = "and",
        as_of: Optional[str] = None,
        where: Optional[dict[str, Any]] = None,
        order_by: Optional[str] = None,
        order_dir: str = "asc",
    ) -> "PaginatedResult":
        """Query entities with filter criteria.

        Args:
            entity_type: Restrict the query to one entity type. ``None``
                queries across all types.
            filter_mode: How to combine filters — "and" (all must match,
                default) or "or" (any may match).
            as_of: Optional ISO-8601 transaction-time. When given, results are
                reconstructed as the graph stood at that time (sec6 §6.8 /
                ADR-0001): entity set, per-entity state, and the computed
                temporal fields are all bound to ``as_of``. Omitted = current.
            where: Optional boolean filter tree (ADR-0006 increment 2) — a
                leaf ``{"field", "op", "value"}`` or ``{"and": [...]}`` /
                ``{"or": [...]}`` / ``{"not": node}``. Validated up front
                (``normalize_where``); composes with ``filters`` by AND.
            order_by: Optional stored-slot name to order by (ADR-0007).
                When given, ordering AND pagination push down to storage
                (SQL ORDER BY / LIMIT / OFFSET; NULLs last, stable ``id``
                tiebreak) and ``total`` comes from a ``COUNT(*)`` under the
                same predicate. Computed temporal fields are not orderable
                (they are provenance-derived, not columns); not combinable
                with ``as_of`` or ``date_from``/``date_to``. Omitted = the
                historical default ordering (``created_at`` ascending,
                computed in Python).
            order_dir: "asc" (default) or "desc"; only used with order_by.
        """
        from mosaic.core.types import PaginatedResult

        if where is not None:
            where = normalize_where(where)
        self._validate_order_args(order_by, order_dir, as_of, date_from, date_to)

        if self._storage is None:
            return PaginatedResult(
                items=[],
                total=0,
                limit=limit or 0,
                offset=offset or 0,
            )

        if order_by is not None:
            # Pushdown path (ADR-0007): storage orders and pages; total is a
            # COUNT(*) under the identical predicate (count ignores
            # limit/offset); temporal fields are derived for the page only.
            query = Query(
                entity_type=entity_type,
                filters=filters or [],
                limit=limit,
                offset=offset,
                filter_mode=filter_mode,
                where=where,
                order_by=order_by,
                order_dir=order_dir,
            )
            page_entities = list(self._storage.find(query))
            total = self._storage.count(query)
            items = self._hydrate_entities(page_entities, as_of=None)
            return PaginatedResult(
                items=items,
                total=total,
                limit=limit or 0,
                offset=offset or 0,
            )

        query = Query(
            entity_type=entity_type,
            filters=filters or [],
            filter_mode=filter_mode,
            where=where,
        )

        # Pass as_of only when set, so adapters whose find() predates the as-of
        # contract (e.g. the LinkML spike) keep working on the current-state path.
        if as_of is not None:
            all_results = list(self._storage.find(query, as_of=as_of))
        else:
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
            temporal_map = self._storage.get_temporal(entity_ids, as_of=as_of)

        filtered = []
        for entity in all_results:
            temporal = temporal_map.get(entity.id)
            if temporal is None and entity_ids:
                from mosaic.core.exceptions import ProvenanceIntegrityError

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
                from mosaic.core.exceptions import ProvenanceIntegrityError

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
                updated_at = temporal.updated_at
                schema_version = temporal.schema_version
                created_by = temporal.created_by
                updated_by = temporal.updated_by
            else:
                created_at = None
                updated_at = None
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
                    "is_available": bool(entity.is_available),
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
        # `is not None`, not truthiness: limit=0 means "zero rows", not
        # "unlimited" — Python's falsy-0 would otherwise return everything
        # (issue #130).
        if limit is not None:
            filtered = filtered[:limit]

        return PaginatedResult(
            items=filtered,
            total=total,
            limit=limit or 0,
            offset=actual_offset,
        )

    @staticmethod
    def _validate_order_args(
        order_by: Optional[str],
        order_dir: str,
        as_of: Optional[str],
        date_from: Optional[str],
        date_to: Optional[str],
    ) -> None:
        """Reject invalid/unsupported order_by combinations up front
        (ADR-0007 gate decisions), before any storage round-trip."""
        from mosaic.core.exceptions import ValidationError

        if order_dir not in ("asc", "desc"):
            raise ValidationError(
                message=(
                    f"order_dir must be 'asc' or 'desc', got {order_dir!r}."
                ),
                field_name="order_dir",
            )
        if order_by is None:
            return
        if as_of is not None:
            raise ValidationError(
                message=(
                    "order_by is not supported together with as_of: ordering "
                    "pushdown targets current-state storage; the "
                    "reconstructed as-of path keeps its documented Python "
                    "ordering (ADR-0007 gate decision)."
                ),
                field_name="order_by",
            )
        if date_from or date_to:
            raise ValidationError(
                message=(
                    "order_by cannot be combined with date_from/date_to: the "
                    "created_at window filters on a computed temporal field "
                    "in Python after materialization, which would page "
                    "before the window applies. Filter on a stored date "
                    "slot instead (ADR-0007)."
                ),
                field_name="order_by",
            )

    def _hydrate_entities(
        self, entities: list, as_of: Optional[str]
    ) -> list[dict[str, Any]]:
        """Convert storage entities to result dicts with computed temporal
        fields — one batch ``get_temporal`` round-trip (sec9 §9.7), loud
        failure on missing provenance (Decision 9.7.A)."""
        entity_ids = [entity.id for entity in entities]
        temporal_map: dict[str, Any] = {}
        if entity_ids and hasattr(self._storage, "get_temporal"):
            temporal_map = self._storage.get_temporal(entity_ids, as_of=as_of)

        items: list[dict[str, Any]] = []
        for entity in entities:
            temporal = temporal_map.get(entity.id)
            if temporal is None and entity_ids:
                from mosaic.core.exceptions import ProvenanceIntegrityError

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
                from mosaic.core.exceptions import ProvenanceIntegrityError

                raise ProvenanceIntegrityError(
                    message=(
                        f"Entity {entity.id!r} has ProvenanceRecord entries "
                        f"but none with operation='create'."
                    ),
                    entity_id=entity.id,
                    inconsistency="missing_create_record",
                )
            items.append(
                {
                    "id": entity.id,
                    "entity_type": entity.entity_type,
                    "data": entity.data,
                    "version": entity.version,
                    "is_available": bool(entity.is_available),
                    "created_at": temporal.created_at if temporal else None,
                    "updated_at": temporal.updated_at if temporal else None,
                    "schema_version": (
                        temporal.schema_version if temporal else None
                    ),
                    "created_by": temporal.created_by if temporal else None,
                    "updated_by": temporal.updated_by if temporal else None,
                    "superseded_by": entity.superseded_by,
                }
            )
        return items

    def count(
        self,
        entity_type: Optional[str] = None,
        filters: Optional[list[dict[str, Any]]] = None,
        filter_mode: str = "and",
        as_of: Optional[str] = None,
        where: Optional[dict[str, Any]] = None,
    ) -> int:
        """Count matching entities without materializing them (ADR-0007).

        Sees exactly what ``query()`` sees under the same criteria
        (availability + filters/where — the availability-consistency rule).
        Under ``as_of`` the count is the length of the reconstructed match
        set (Python-path semantics, same as ``query(as_of=...).total``).
        """
        if where is not None:
            where = normalize_where(where)
        if self._storage is None:
            return 0
        query = Query(
            entity_type=entity_type,
            filters=filters or [],
            filter_mode=filter_mode,
            where=where,
        )
        if as_of is not None:
            return self._storage.count(query, as_of=as_of)
        return self._storage.count(query)

    def facet_counts(
        self,
        entity_type: str,
        field: str,
        filters: Optional[list[dict[str, Any]]] = None,
        filter_mode: str = "and",
        where: Optional[dict[str, Any]] = None,
    ) -> list[tuple]:
        """Per-value counts for ``field`` under the given criteria —
        ``[(value, count), ...]``, count desc then value asc (ADR-0007).

        Entities with no stored value for ``field`` are not counted
        (absence is queried with ``is_null``). Availability-consistent:
        buckets sum over exactly the entities ``query()`` would return.
        Not defined under as-of in this increment.
        """
        if where is not None:
            where = normalize_where(where)
        if self._storage is None:
            return []
        query = Query(
            entity_type=entity_type,
            filters=filters or [],
            filter_mode=filter_mode,
            where=where,
        )
        return list(self._storage.facet_counts(query, field))

    def field_range(
        self,
        entity_type: str,
        field: str,
        filters: Optional[list[dict[str, Any]]] = None,
        filter_mode: str = "and",
        where: Optional[dict[str, Any]] = None,
    ) -> tuple:
        """``(min, max)`` of ``field`` under the given criteria (ADR-0007);
        ``(None, None)`` when no matching entity has a value. Not defined
        under as-of in this increment."""
        if where is not None:
            where = normalize_where(where)
        if self._storage is None:
            return (None, None)
        query = Query(
            entity_type=entity_type,
            filters=filters or [],
            filter_mode=filter_mode,
            where=where,
        )
        return tuple(self._storage.field_range(query, field))

    def query_updated_since(
        self,
        entity_type: Optional[str] = None,
        since: str = "",
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        filters: Optional[list[dict[str, Any]]] = None,
    ) -> "PaginatedResult":
        """Query entities updated after a watermark timestamp (sec4 §4.5).

        Designed for polling callers (e.g. Cappella's ``hippo_poll``
        trigger). Selects entities whose provenance-derived ``updated_at``
        is strictly greater than ``since`` and orders results by
        ``updated_at`` ascending — oldest first, so callers can process
        in order and persist the last ``updated_at`` they saw as the
        watermark for the next poll.

        ``since`` is compared against Hippo's server-side provenance
        timestamps (UTC); callers should never use their own clock. The
        watermark filter runs over the same provenance-derived read path
        :meth:`query` uses (mirroring its ``date_from``/``date_to`` in-Python
        pattern); pushing it into the ``entity_provenance_summary`` view
        (sec6 §6.6) is the documented optimization if polling volume grows.

        Args:
            entity_type: Restrict the poll to one entity type. ``None``
                polls across all types (composes with the issue #44/#49
                cross-class scan).
            since: ISO 8601 timestamp watermark (exclusive).
            limit: Maximum number of results to return.
            offset: Number of results to skip.
            filters: Optional additional field filters (AND-composed).

        Raises:
            TemporalQueryError: If ``since`` is not a parseable ISO 8601
                timestamp.
        """
        from mosaic.core.exceptions import TemporalQueryError
        from mosaic.core.types import PaginatedResult

        since_dt = self._parse_iso_timestamp(since)
        if since_dt is None:
            raise TemporalQueryError(
                message=(
                    f"updated_since must be an ISO 8601 timestamp; got {since!r}"
                ),
                requested_timestamp=since,
            )

        base = self.query(entity_type, filters=filters)

        matched: list[tuple[Any, dict[str, Any]]] = []
        for item in base.items:
            updated = self._parse_iso_timestamp(
                item.get("updated_at") or item.get("created_at") or ""
            )
            if updated is not None and updated > since_dt:
                matched.append((updated, item))

        matched.sort(key=lambda pair: pair[0])
        sorted_items = [item for _, item in matched]

        total = len(sorted_items)
        actual_offset = offset or 0
        if actual_offset:
            sorted_items = sorted_items[actual_offset:]
        if limit is not None:  # limit=0 means zero rows, not unlimited (#130)
            sorted_items = sorted_items[:limit]

        return PaginatedResult(
            items=sorted_items,
            total=total,
            limit=limit or 0,
            offset=actual_offset,
        )

    @staticmethod
    def _parse_iso_timestamp(value: str) -> Optional["datetime"]:
        """Parse an ISO 8601 timestamp, normalizing ``Z`` and naive values to UTC."""
        from datetime import datetime, timezone

        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

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
