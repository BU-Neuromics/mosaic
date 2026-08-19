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
        where: Optional[Dict[str, Any]] = None,
    ):
        self.entity_type = entity_type
        self.filters = filters or []
        self.limit = limit
        self.offset = offset
        self.filter_mode = filter_mode  # "and" or "or"
        # Optional boolean filter tree (ADR-0006 increment 2): a node is a
        # leaf {"field", "op", "value"} or {"and": [...]}/{"or": [...]}/
        # {"not": node}. Composes with ``filters`` by AND. Validate with
        # ``normalize_where``.
        self.where = where


# Filter ops recognized by ``normalize_filter`` / adapter predicate builders.
# "eq" is the historical (and default) behavior; "in" is set membership
# (issue #102); the comparison set (neq/gt/gte/lt/lte/contains/is_null) is
# ADR-0006 increment 1 (issue #155). Every op named here must be implemented
# by BOTH adapters' SQL builders AND by ``matches_operator`` (the shared
# Python-side evaluator behind the as-of mirrors) — an op present in one but
# not the other silently forks current-state and as-of results.
VALID_FILTER_OPS = {
    "eq",
    "in",
    "neq",
    "gt",
    "gte",
    "lt",
    "lte",
    "contains",
    "is_null",
}

#: Ops whose SQL rendering is a plain binary comparison on the column value.
COMPARISON_SQL_OPS = {"neq": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}


def escape_like(value: str) -> str:
    """Escape ``%``/``_``/``\\`` in a LIKE pattern fragment (ESCAPE ``\\``)."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def matches_operator(actual: Any, op: str, value: Any) -> bool:
    """Evaluate one ``(actual, op, value)`` predicate in Python.

    The single shared evaluator behind every as-of ``_matches_filters``
    mirror (SQLite and Postgres), kept deliberately aligned with the SQL
    builders' semantics so as-of queries never diverge from current-state
    queries (ADR-0006):

    - ``is_null`` is the only op that addresses absence: ``value`` is a
      bool; ``True`` matches entities with no stored value for the field.
    - Every other op follows SQL NULL semantics — a missing/``None`` actual
      (or a ``None`` filter value) matches nothing. In particular
      ``eq`` with ``None`` matches nothing (the SQL builders emit
      ``col = NULL``, which is never true); use ``is_null`` instead.
    - ``contains`` is case-insensitive substring match (SQL: ``LIKE``/
      ``ILIKE``). Note SQLite's LIKE is case-insensitive for ASCII only;
      non-ASCII case folding may differ per backend.
    - ``gt``/``gte``/``lt``/``lte`` compare natively; date/datetime slots
      store ISO-8601 strings, which order lexicographically. A type
      mismatch matches nothing rather than raising (SQL comparisons on
      mistyped text likewise fail to match).
    """
    if op == "is_null":
        return (actual is None) if value else (actual is not None)
    if actual is None or value is None:
        return False
    if op == "in":
        if not value:
            return False
        return actual in value
    if op == "eq":
        return actual == value
    if op == "neq":
        return actual != value
    if op == "contains":
        return str(value).lower() in str(actual).lower()
    if op in COMPARISON_SQL_OPS:
        try:
            if op == "gt":
                return actual > value
            if op == "gte":
                return actual >= value
            if op == "lt":
                return actual < value
            return actual <= value
        except TypeError:
            return False
    return False


def normalize_filter(f: Dict[str, Any]) -> List[tuple]:
    """Normalize one ``Query.filters`` entry to ``[(field, op, value), ...]``.

    Accepts both filter-dict shapes in use across the codebase:

    - Canonical: ``{"field": ..., "value": ..., "op": ...}``. ``op`` is
      optional and defaults to ``"eq"``. It must name a supported operator
      (:data:`VALID_FILTER_OPS`); an unsupported ``op`` (``"ne"``,
      ``"starts_with"``, ...) raises
      :class:`~mosaic.core.exceptions.ValidationError` rather than silently
      degrading to equality — the highest-risk failure for a query API, since
      ``ne`` would otherwise return the *inverse* of what was asked (issue
      #129). ``is_null`` additionally requires a boolean ``value`` and
      ``in`` a list/tuple ``value``, validated here for the same
      loud-over-wrong reason. Yields a single ``(field, op, value)`` triple.
    - Bare shorthand: ``{field_name: value, ...}``, always ``"eq"``.
      Yields one triple per key (historically each key of a shorthand
      dict is an independent AND'd sub-filter — see the adapters'
      pre-existing ``for key, value in f.items()`` loops).

    The operator key is ``op``. A canonical dict that carries ``operator``
    (the field name on :class:`~mosaic.core.types.FilterCondition`, a very
    plausible slip) but no ``op`` raises rather than silently defaulting to
    ``eq`` (issue #129).
    """
    if "field" in f and "value" in f:
        if "op" not in f and "operator" in f:
            from mosaic.core.exceptions import ValidationError

            raise ValidationError(
                message=(
                    f"Filter on field {f['field']!r} uses key 'operator'; the "
                    f"query filter-dict operator key is 'op'. Use "
                    f"{{'field': ..., 'op': ..., 'value': ...}}. ('operator' is "
                    f"the FilterCondition model field name, not the "
                    f"filter-dict key.)"
                ),
                field_name=f["field"],
            )
        return [validate_leaf(f["field"], f.get("op", "eq"), f["value"])]
    return [(key, "eq", value) for key, value in f.items()]


def validate_leaf(field: str, op: str, value: Any) -> tuple:
    """Validate one ``(field, op, value)`` predicate; return it canonical.

    The single leaf-validation chokepoint behind both the flat
    ``normalize_filter`` path and the ``normalize_where`` tree path:
    unknown operators, non-boolean ``is_null`` values, and non-list ``in``
    values raise loudly (issue #129's loud-over-wrong rule).
    """
    if op not in VALID_FILTER_OPS:
        from mosaic.core.exceptions import ValidationError

        raise ValidationError(
            message=(
                f"Unsupported filter operator {op!r} on field "
                f"{field!r}. Implemented operators: "
                f"{sorted(VALID_FILTER_OPS)}. Operators such as "
                f"'ne'/'starts_with' are not supported and unsupported "
                f"ops once degraded silently to equality (issue #129); "
                f"they now raise so callers are never handed wrong "
                f"results."
            ),
            field_name=field,
        )
    if op == "is_null" and not isinstance(value, bool):
        from mosaic.core.exceptions import ValidationError

        raise ValidationError(
            message=(
                f"Filter op 'is_null' on field {field!r} requires a "
                f"boolean value (True = match entities with no stored "
                f"value), got {type(value).__name__}."
            ),
            field_name=field,
        )
    if op == "in" and not isinstance(value, (list, tuple)):
        from mosaic.core.exceptions import ValidationError

        raise ValidationError(
            message=(
                f"Filter op 'in' on field {field!r} requires a "
                f"list of candidate values, got {type(value).__name__}."
            ),
            field_name=field,
        )
    return (field, op, value)


#: Defensive recursion bound for ``normalize_where``/``matches_tree``.
#: Transports enforce their own (smaller) caps with coded errors; this one
#: only prevents stack abuse through the raw SDK.
MAX_WHERE_DEPTH = 32


def normalize_where(node: Dict[str, Any], *, _depth: int = 1) -> Dict[str, Any]:
    """Validate a ``Query.where`` boolean filter tree; return it canonical.

    A node is exactly one of (ADR-0006 increment 2):

    - a **leaf**: ``{"field": ..., "op": ..., "value": ...}`` (``op``
      optional, default ``"eq"``; validated by :func:`validate_leaf`);
    - ``{"and": [node, ...]}`` / ``{"or": [node, ...]}`` — non-empty lists
      (an empty combinator is ambiguous and raises);
    - ``{"not": node}``.

    Trees compose with the flat ``Query.filters`` by AND. Malformed shapes
    raise :class:`~mosaic.core.exceptions.ValidationError` — the storage
    layer never guesses at intent.
    """
    from mosaic.core.exceptions import ValidationError

    if _depth > MAX_WHERE_DEPTH:
        raise ValidationError(
            message=(
                f"Filter tree exceeds the maximum nesting depth "
                f"({MAX_WHERE_DEPTH})."
            ),
            field_name="where",
        )
    if not isinstance(node, dict):
        raise ValidationError(
            message=(
                f"Filter tree node must be a dict (leaf or and/or/not "
                f"combinator), got {type(node).__name__}."
            ),
            field_name="where",
        )
    combinators = [k for k in ("and", "or", "not") if k in node]
    if combinators:
        if len(node) != 1:
            raise ValidationError(
                message=(
                    f"Filter tree combinator node must have exactly one key; "
                    f"got {sorted(node)}."
                ),
                field_name="where",
            )
        key = combinators[0]
        if key == "not":
            return {"not": normalize_where(node["not"], _depth=_depth + 1)}
        children = node[key]
        if not isinstance(children, (list, tuple)) or not children:
            raise ValidationError(
                message=(
                    f"Filter tree {key!r} combinator requires a non-empty "
                    f"list of child nodes."
                ),
                field_name="where",
            )
        return {
            key: [normalize_where(c, _depth=_depth + 1) for c in children]
        }
    if "field" in node and "value" in node:
        field, op, value = validate_leaf(
            node["field"], node.get("op", "eq"), node["value"]
        )
        return {"field": field, "op": op, "value": value}
    raise ValidationError(
        message=(
            f"Filter tree node is neither a leaf ({{field, op, value}}) nor "
            f"a combinator ({{and|or|not}}); got keys {sorted(node)}."
        ),
        field_name="where",
    )


def matches_tree(
    data: Dict[str, Any], entity_id: str, node: Dict[str, Any]
) -> bool:
    """Evaluate a normalized ``where`` tree against a data dict in Python.

    The tree analogue of :func:`matches_operator` — the shared as-of mirror
    evaluator, kept aligned with the adapters' SQL tree compilers
    (ADR-0006). ``node`` must be normalized (:func:`normalize_where`).
    """
    if "and" in node:
        return all(matches_tree(data, entity_id, c) for c in node["and"])
    if "or" in node:
        return any(matches_tree(data, entity_id, c) for c in node["or"])
    if "not" in node:
        return not matches_tree(data, entity_id, node["not"])
    field = node["field"]
    actual = entity_id if field == "id" else data.get(field)
    return matches_operator(actual, node["op"], node["value"])


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
    "VALID_FILTER_OPS",
    "COMPARISON_SQL_OPS",
    "MAX_WHERE_DEPTH",
    "normalize_filter",
    "normalize_where",
    "validate_leaf",
    "matches_operator",
    "matches_tree",
    "escape_like",
]
