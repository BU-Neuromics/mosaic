"""Error types for preset validation violations."""

from dataclasses import dataclass
from typing import Any


@dataclass
class ValidationError:
    """Base class for preset validation errors.

    Attributes:
        field_path: The dot-notation path to the field.
        message: Human-readable error message.
    """

    field_path: str
    message: str


@dataclass
class ReferenceConstraintViolation(ValidationError):
    """Error when a reference constraint is violated.

    Raised when a referenced entity does not exist.
    """

    referenced_entity_type: str | None = None
    referenced_entity_id: str | None = None

    def __init__(
        self,
        field_path: str,
        message: str,
        referenced_entity_type: str | None = None,
        referenced_entity_id: str | None = None,
    ):
        super().__init__(field_path=field_path, message=message)
        self.referenced_entity_type = referenced_entity_type
        self.referenced_entity_id = referenced_entity_id


@dataclass
class CountConstraintViolation(ValidationError):
    """Error when a count constraint is violated.

    Raised when a collection exceeds the allowed count limit.
    """

    actual_count: int | None = None
    max_count: int | None = None

    def __init__(
        self,
        field_path: str,
        message: str,
        actual_count: int | None = None,
        max_count: int | None = None,
    ):
        super().__init__(field_path=field_path, message=message)
        self.actual_count = actual_count
        self.max_count = max_count


@dataclass
class ImmutableFieldViolation(ValidationError):
    """Error when an immutable field is modified.

    Raised when an attempt is made to change a field marked as immutable.
    """

    old_value: Any = None
    new_value: Any = None

    def __init__(
        self,
        field_path: str,
        message: str,
        old_value: Any = None,
        new_value: Any = None,
    ):
        super().__init__(field_path=field_path, message=message)
        self.old_value = old_value
        self.new_value = new_value


@dataclass
class FieldRequiredViolation(ValidationError):
    """Error when a required field is missing.

    Raised when a conditionally required field is not present.
    """

    condition: str | None = None

    def __init__(
        self,
        field_path: str,
        message: str,
        condition: str | None = None,
    ):
        super().__init__(field_path=field_path, message=message)
        self.condition = condition


@dataclass
class SelfReferenceViolation(ValidationError):
    """Error when a self-reference is detected.

    Raised when an entity references itself.
    """

    self_reference_id: str | None = None

    def __init__(
        self,
        field_path: str,
        message: str,
        self_reference_id: str | None = None,
    ):
        super().__init__(field_path=field_path, message=message)
        self.self_reference_id = self_reference_id


class ErrorMessageBuilder:
    """Builder for constructing error messages for preset violations."""

    @staticmethod
    def reference_violation(
        field_path: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> str:
        """Build error message for reference constraint violation.

        Args:
            field_path: The field path that failed validation.
            entity_type: The type of entity being referenced.
            entity_id: The ID of the referenced entity.

        Returns:
            Formatted error message.
        """
        if entity_type and entity_id:
            return (
                f"Reference constraint violation: field '{field_path}' "
                f"references non-existent entity '{entity_type}' with ID '{entity_id}'"
            )
        return f"Reference constraint violation: field '{field_path}' references non-existent entity"

    @staticmethod
    def count_violation(
        field_path: str, actual: int | None = None, max_count: int | None = None
    ) -> str:
        """Build error message for count constraint violation.

        Args:
            field_path: The field path that failed validation.
            actual: The actual count of items.
            max_count: The maximum allowed count.

        Returns:
            Formatted error message.
        """
        if actual is not None and max_count is not None:
            return (
                f"Count constraint violation: field '{field_path}' has {actual} items, "
                f"exceeds maximum of {max_count}"
            )
        return f"Count constraint violation: field '{field_path}' exceeds allowed count"

    @staticmethod
    def immutable_field(field_path: str) -> str:
        """Build error message for immutable field violation.

        Args:
            field_path: The field path that failed validation.

        Returns:
            Formatted error message.
        """
        return f"Immutable field violation: field '{field_path}' cannot be modified"

    @staticmethod
    def field_required(field_path: str, condition: str | None = None) -> str:
        """Build error message for required field violation.

        Args:
            field_path: The field path that failed validation.
            condition: The condition that requires the field.

        Returns:
            Formatted error message.
        """
        if condition:
            return (
                f"Field required violation: field '{field_path}' is required "
                f"when {condition}"
            )
        return f"Field required violation: field '{field_path}' is required"

    @staticmethod
    def self_reference(field_path: str, entity_id: str | None = None) -> str:
        """Build error message for self-reference violation.

        Args:
            field_path: The field path that failed validation.
            entity_id: The ID of the entity referencing itself.

        Returns:
            Formatted error message.
        """
        if entity_id:
            return (
                f"Self-reference violation: field '{field_path}' contains "
                f"self-reference to entity '{entity_id}'"
            )
        return f"Self-reference violation: field '{field_path}' contains self-reference"
