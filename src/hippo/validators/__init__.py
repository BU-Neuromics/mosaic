"""Schema validator for write operations."""

from hippo.core.validation import (
    ValidationResult,
    WriteOperation,
    WriteValidator,
)


class SchemaValidator(WriteValidator):
    """Validator that checks entity data conforms to defined schema.

    This is a placeholder implementation that validates all operations succeed.
    """

    @property
    def priority(self) -> int:
        return 5

    def validate(self, operation: WriteOperation) -> ValidationResult:
        """Validate the write operation against the schema.

        Args:
            operation: The write operation to validate.

        Returns:
            ValidationResult indicating success or failure with errors.
        """
        if not operation.data:
            return ValidationResult(is_valid=False, errors=["Data cannot be empty"])
        return ValidationResult(is_valid=True, errors=[])
