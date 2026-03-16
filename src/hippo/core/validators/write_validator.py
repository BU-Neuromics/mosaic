"""CEL Validator Engine - Write Validator Integration."""

from typing import Any, Optional

from hippo.core.validation.validators import (
    ValidationResult,
    WriteOperation,
    WriteValidator,
)
from hippo.core.validators.engine import ValidationResult as EngineValidationResult
from hippo.core.validators.engine import ValidatorEngine


class CELWriteValidator(WriteValidator):
    """WriteValidator integration for CEL validator engine.

    Loads validators from validators.yaml and evaluates them against
    write operations using the CEL validator engine.
    """

    def __init__(
        self,
        validators_path: Optional[str] = None,
        engine: Optional[ValidatorEngine] = None,
    ):
        """Initialize CEL write validator.

        Args:
            validators_path: Path to validators.yaml. If not provided,
                the validator will need to be loaded manually.
            engine: Pre-configured ValidatorEngine instance.
        """
        self._engine = engine
        if validators_path and self._engine is None:
            self._engine = ValidatorEngine()
            self._engine.load(validators_path)

    @property
    def priority(self) -> int:
        """Priority of the validator.

        CEL validators run after schema validation (priority -1) but before
        plugin validators. Default priority is 0.
        """
        return 0

    def validate(self, operation: WriteOperation) -> ValidationResult:
        """Validate a write operation using CEL rules.

        Args:
            operation: The write operation to validate.

        Returns:
            ValidationResult indicating success or failure with errors.
        """
        if self._engine is None or not self._engine.is_loaded:
            return ValidationResult(is_valid=True, errors=[])

        entity_type = operation.entity_type
        op_type = self._map_operation(operation.operation)

        engine_result = self._engine.validate(
            entity_type=entity_type,
            operation=op_type,
            entity_data=operation.data,
            existing_entity=None,
        )

        return self._convert_result(engine_result, operation)

    def _map_operation(self, operation: str) -> str:
        """Map WriteOperation operation to validator operation.

        Args:
            operation: The operation type from WriteOperation.

        Returns:
            The mapped operation type for validators.
        """
        if operation == "insert":
            return "create"
        return operation

    def _convert_result(
        self,
        engine_result: EngineValidationResult,
        operation: WriteOperation,
    ) -> ValidationResult:
        """Convert engine validation result to WriteValidator result.

        Args:
            engine_result: The engine validation result.
            operation: The original write operation.

        Returns:
            Converted ValidationResult.
        """
        error_messages = []
        for error in engine_result.errors:
            msg = error.get("message", "Validation failed")
            error_messages.append(msg)

        return ValidationResult(
            is_valid=engine_result.is_valid,
            errors=error_messages,
            entity_id=operation.data.get("id"),
        )

    def set_engine(self, engine: ValidatorEngine) -> None:
        """Set the validator engine.

        Args:
            engine: The ValidatorEngine to use.
        """
        self._engine = engine

    def get_engine(self) -> Optional[ValidatorEngine]:
        """Get the validator engine.

        Returns:
            The ValidatorEngine or None if not loaded.
        """
        return self._engine
