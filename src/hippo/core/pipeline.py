"""Validation pipeline for Hippo write operations.

Provides a sequential pipeline that executes validators in order with fail-fast behavior.
"""

from hippo.core.validation.validators import (
    ValidationResult,
    WriteOperation,
    WriteValidator,
)


class ValidationPipeline:
    """Pipeline for executing validators in sequential order.

    Executes registered validators in order with fail-fast behavior by default.
    Supports exactly-once execution guarantee per validator per operation.
    """

    def __init__(self) -> None:
        self._validators: list[WriteValidator] = []
        self._executed_ids: set[int] = set()

    def add_validator(self, validator: WriteValidator) -> None:
        """Register a validator to the pipeline.

        Args:
            validator: The validator to add.
        """
        self._validators.append(validator)

    def clear_validators(self) -> None:
        """Clear all registered validators."""
        self._validators.clear()
        self._executed_ids.clear()

    def execute(self, operation: WriteOperation) -> ValidationResult:
        """Execute validators in sequential fail-fast order.

        Stops execution on first validation failure and returns immediately.

        Args:
            operation: The write operation to validate.

        Returns:
            ValidationResult with success or first failure.
        """
        self._executed_ids.clear()

        for idx, validator in enumerate(self._validators):
            self._executed_ids.add(idx)
            try:
                result = validator.validate(operation)
            except Exception as e:
                return ValidationResult(
                    is_valid=False,
                    errors=[
                        f"Validator '{type(validator).__name__}' raised exception: {str(e)}"
                    ],
                    entity_id=operation.data.get("id") if operation.data else None,
                )

            if not result.is_valid:
                return ValidationResult(
                    is_valid=False,
                    errors=result.errors,
                    entity_id=result.entity_id
                    or (operation.data.get("id") if operation.data else None),
                )

        return ValidationResult(
            is_valid=True,
            errors=[],
            entity_id=operation.data.get("id") if operation.data else None,
        )

    def execute_all(self, operation: WriteOperation) -> ValidationResult:
        """Execute all validators and report all failures.

        Unlike execute(), this method runs all validators regardless of failures
        and aggregates all errors into a single result.

        Args:
            operation: The write operation to validate.

        Returns:
            ValidationResult with aggregated success/failure and all errors.
        """
        self._executed_ids.clear()
        all_errors: list[str] = []
        entity_id: str | None = None

        for idx, validator in enumerate(self._validators):
            self._executed_ids.add(idx)

            try:
                result = validator.validate(operation)
            except Exception as e:
                all_errors.append(
                    f"Validator '{type(validator).__name__}' raised exception: {str(e)}"
                )
                continue

            if not result.is_valid:
                all_errors.extend(result.errors)
                if entity_id is None and result.entity_id:
                    entity_id = result.entity_id

        if entity_id is None and operation.data:
            entity_id = operation.data.get("id")

        return ValidationResult(
            is_valid=len(all_errors) == 0,
            errors=all_errors,
            entity_id=entity_id,
        )

    def get_validator_count(self) -> int:
        """Get the number of registered validators.

        Returns:
            Count of validators in the pipeline.
        """
        return len(self._validators)

    def get_validators(self) -> list[WriteValidator]:
        """Get all registered validators in order.

        Returns:
            List of validators in execution order.
        """
        return list(self._validators)


def create_pipeline(
    validators: list[WriteValidator] | None = None,
) -> ValidationPipeline:
    """Create a validation pipeline with optional pre-registered validators.

    Args:
        validators: Optional list of validators to register.

    Returns:
        Configured ValidationPipeline instance.
    """
    pipeline = ValidationPipeline()
    if validators:
        for validator in validators:
            pipeline.add_validator(validator)
    return pipeline
