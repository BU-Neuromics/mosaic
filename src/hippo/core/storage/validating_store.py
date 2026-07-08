"""Mixin to integrate validation pipeline with EntityStore."""

from typing import Any, List

from hippo.core.storage import EntityStore, ScoredMatch
from hippo.core.validation import (
    ValidationResult,
    ValidatorPipeline,
    WriteOperation,
    WriteValidator,
)


class ValidatingEntityStore(EntityStore):
    """Wrapper that adds validation to any EntityStore.

    Wraps create() and update() methods to run validators before
    executing the underlying operations.
    """

    def __init__(
        self,
        store: EntityStore,
        pipeline: ValidatorPipeline | None = None,
    ) -> None:
        self._store = store
        self._pipeline = pipeline or ValidatorPipeline()

    def _validate_operation(
        self, operation: str, entity: Any, data: dict[str, Any]
    ) -> ValidationResult:
        """Validate a write operation.

        Args:
            operation: Type of operation (create, update, delete).
            entity: The entity being operated on.
            data: The data for the operation.

        Returns:
            ValidationResult with any validation errors.
        """
        write_op = WriteOperation(
            operation=operation,
            entity_type=type(entity).__name__,
            data=data,
        )
        return self._pipeline.validate(write_op)

    def create(self, entity: Any) -> Any:
        """Create a new entity with validation."""
        data = {"id": getattr(entity, "id", None), **vars(entity)}
        result = self._validate_operation("insert", entity, data)
        if not result.is_valid:
            from hippo.core.exceptions import ValidationError

            raise ValidationError(f"Validation failed: {', '.join(result.errors)}")
        return self._store.create(entity)

    def read(self, entity_id: str) -> Any | None:
        """Read an entity by its ID."""
        return self._store.read(entity_id)

    def update(self, entity: Any) -> Any:
        """Update an existing entity with validation."""
        data = vars(entity)
        result = self._validate_operation("update", entity, data)
        if not result.is_valid:
            from hippo.core.exceptions import ValidationError

            raise ValidationError(f"Validation failed: {', '.join(result.errors)}")
        return self._store.update(entity)

    def delete(self, entity_id: str) -> bool:
        """Delete an entity by its ID."""
        return self._store.delete(entity_id)

    def find(self, query: Any, *, as_of: Any = None) -> Any:
        """Find entities matching a query."""
        return self._store.find(query, as_of=as_of)

    def history(self, entity_id: str) -> Any:
        """Delegate provenance history to the wrapped store (sec6 §6.7)."""
        return self._store.history(entity_id)

    def state_at(self, entity_id: str, timestamp: str) -> Any:
        """Delegate as-of state reconstruction to the wrapped store (sec6 §6.8)."""
        return self._store.state_at(entity_id, timestamp)

    def get_temporal(self, entity_ids: List[str], *, as_of: Any = None) -> Any:
        """Delegate temporal-field derivation to the wrapped store (sec6 §6.8)."""
        return self._store.get_temporal(entity_ids, as_of=as_of)

    def findAll(self) -> Any:
        """Find all entities."""
        return self._store.findAll()

    def findBy(self, **kwargs: Any) -> Any:
        """Find entities by field values."""
        return self._store.findBy(**kwargs)

    def track_creation(self, entity: Any, metadata: dict[str, Any]) -> Any:
        """Track the creation of an entity."""
        return self._store.track_creation(entity, metadata)

    def track_update(self, entity: Any, metadata: dict[str, Any]) -> Any:
        """Track the update of an entity."""
        return self._store.track_update(entity, metadata)

    def track_deletion(self, entity_id: str, metadata: dict[str, Any]) -> Any:
        """Track the deletion of an entity."""
        return self._store.track_deletion(entity_id, metadata)

    def search(
        self,
        query: str,
        entity_type: str,
        field_name: str,
        min_score: float = 0.0,
        limit: int = 100,
    ) -> List[ScoredMatch]:
        """Search entities using full-text search."""
        return self._store.search(
            query, entity_type, field_name, min_score=min_score, limit=limit
        )

    def search_capabilities(self) -> set[str]:
        """Return the set of search modes supported by the underlying store."""
        return self._store.search_capabilities()
