"""Validation module for Hippo."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from typing import Any, Iterable, Iterator


@dataclass
class ValidationResult:
    """Result of a validation operation.

    Attributes:
        is_valid: Whether validation passed.
        errors: List of error messages.
        entity_id: Optional entity ID for context.
    """

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    entity_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.is_valid, bool):
            raise TypeError("is_valid must be a boolean")
        if isinstance(self.errors, str):
            self.errors = [self.errors]
        elif not isinstance(self.errors, Iterable):
            raise TypeError("errors must be an iterable")
        elif not isinstance(self.errors, list):
            self.errors = list(self.errors)
        if self.entity_id is not None and not isinstance(self.entity_id, str):
            raise TypeError("entity_id must be a string or None")


@dataclass
class WriteOperation:
    """Represents a write operation to be validated.

    Attributes:
        operation: Type of operation (insert, update, delete).
        entity_type: The type of entity being operated on.
        data: The data to be written.
    """

    operation: str
    entity_type: str
    data: dict[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.operation, str):
            raise TypeError("operation must be a string")
        if not isinstance(self.entity_type, str):
            raise TypeError("entity_type must be a string")
        if not isinstance(self.data, dict):
            raise TypeError("data must be a dictionary")


class WriteValidator(ABC):
    """Abstract base class for write operation validators.

    Subclasses must implement the validate method.
    """

    @property
    def priority(self) -> int:
        """Priority of the validator.

        Higher priority validators execute first.
        Defaults to 0.
        """
        return 0

    @abstractmethod
    def validate(self, operation: WriteOperation) -> ValidationResult:
        """Validate a write operation.

        Args:
            operation: The write operation to validate.

        Returns:
            ValidationResult indicating success or failure with errors.
        """
        ...


ENTRY_POINT_GROUP = "hippo.write_validators"


class ValidatorRegistry:
    """Registry for discovering and managing write validators via entry points.

    Discovers validators registered via the 'hippo.write_validators' entry point group
    and orders them by priority (highest first).
    """

    def __init__(self) -> None:
        self._validators: list[WriteValidator] = []
        self._discovered = False

    def _discover_validators(self) -> None:
        """Discover validators from entry points."""
        self._validators = []
        eps = entry_points()
        try:
            if hasattr(eps, "select"):
                validator_eps = eps.select(group=ENTRY_POINT_GROUP)
            else:
                validator_eps = list(eps.get(ENTRY_POINT_GROUP, []))  # type: ignore[union-attr]
        except TypeError:
            validator_eps = []

        for ep in validator_eps:
            try:
                validator = ep.load()
                self._validators.append(validator())
            except Exception:
                pass

        self._validators.sort(key=lambda v: v.priority, reverse=True)
        self._discovered = True

    def get_validators(self) -> list[WriteValidator]:
        """Get all discovered validators ordered by priority (highest first).

        Returns:
            List of WriteValidator instances ordered by priority descending.
        """
        if not self._discovered:
            self._discover_validators()
        return self._validators

    def discover(self) -> list[WriteValidator]:
        """Force rediscovery of validators from entry points.

        Returns:
            List of WriteValidator instances ordered by priority descending.
        """
        self._discovered = False
        return self.get_validators()


class ValidatorPipeline:
    """Pipeline for executing validators in priority order.

    Executes all registered validators in order (highest priority first)
    and aggregates results.
    """

    def __init__(self, registry: ValidatorRegistry | None = None) -> None:
        self._registry = registry or ValidatorRegistry()

    def execute(self, operation: WriteOperation) -> list[ValidationResult]:
        """Execute all validators in priority order.

        Args:
            operation: The write operation to validate.

        Returns:
            List of ValidationResult from each validator (in execution order).
        """
        results: list[ValidationResult] = []
        validators = self._registry.get_validators()
        for validator in validators:
            result = validator.validate(operation)
            results.append(result)
        return results

    def validate(self, operation: WriteOperation) -> ValidationResult:
        """Execute all validators and aggregate results.

        Args:
            operation: The write operation to validate.

        Returns:
            ValidationResult with aggregated success/failure and all errors.
        """
        results = self.execute(operation)
        all_errors: list[str] = []
        for result in results:
            all_errors.extend(result.errors)
        return ValidationResult(
            is_valid=all(r.is_valid for r in results),
            errors=all_errors,
        )
