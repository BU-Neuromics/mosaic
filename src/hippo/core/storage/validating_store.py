"""Mixin to integrate validation pipeline with EntityStore."""

from typing import Any, Generic, TypeVar

from hippo.core.storage import Entity, EntityStore
from hippo.core.validation import (
    ValidationResult,
    ValidatorPipeline,
    WriteOperation,
    WriteValidator,
)

T = TypeVar("T", bound=Entity)


class ValidatingEntityStore(EntityStore[T]):
    """Wrapper that adds validation to any EntityStore.

    Wraps create() and update() methods to run validators before
    executing the underlying operations.
    """

    def __init__(
        self,
        store: EntityStore[T],
        pipeline: ValidatorPipeline | None = None,
    ) -> None:
        self._store = store
        self._pipeline = pipeline or ValidatorPipeline()

    def _validate_operation(
        self, operation: str, entity: T, data: dict[str, Any]
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

    def create(self, entity: T) -> T:
        """Create a new entity with validation."""
        data = {"id": getattr(entity, "id", None), **vars(entity)}
        result = self._validate_operation("insert", entity, data)
        if not result.is_valid:
            from hippo.core.exceptions import ValidationError

            raise ValidationError(f"Validation failed: {', '.join(result.errors)}")
        return self._store.create(entity)

    def read(self, entity_id: str) -> T | None:
        """Read an entity by its ID."""
        return self._store.read(entity_id)

    def update(self, entity: T) -> T:
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

    def find(self, query: Any) -> Any:
        """Find entities matching a query."""
        return self._store.find(query)

    def findAll(self) -> Any:
        """Find all entities."""
        return self._store.findAll()

    def findBy(self, **kwargs: Any) -> Any:
        """Find entities by field values."""
        return self._store.findBy(**kwargs)

    def track_creation(self, entity: T, metadata: dict[str, Any]) -> Any:
        """Track the creation of an entity."""
        return self._store.track_creation(entity, metadata)

    def track_update(self, entity: T, metadata: dict[str, Any]) -> Any:
        """Track the update of an entity."""
        return self._store.track_update(entity, metadata)

    def track_deletion(self, entity_id: str, metadata: dict[str, Any]) -> Any:
        """Track the deletion of an entity."""
        return self._store.track_deletion(entity_id, metadata)
