"""Schema validator for Hippo write operations."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from hippo.core.validation.validators import (
    ValidationResult,
    WriteOperation,
    WriteValidator,
)
from hippo.config.models import FieldDefinition, SchemaConfig


ENTITY_REFERENCE_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
TIMESTAMP_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?)?$"
)


@dataclass
class SchemaValidationConfig:
    """Configuration for schema validation.

    Attributes:
        schemas: Dictionary mapping entity type names to SchemaConfig.
        entity_exists_fn: Optional callable that checks if an entity exists.
            Signature: (entity_type: str, entity_id: str) -> bool
    """

    schemas: dict[str, SchemaConfig] = field(default_factory=dict)
    entity_exists_fn: Callable[[str, str], bool] | None = None


class SchemaValidator(WriteValidator):
    """Validator that checks entity data conforms to defined schema.

    Validates write operations against schema definitions including:
    - Required fields
    - Type constraints (string, number, boolean, timestamp)
    - Enum values
    - Reference existence
    - Nested field validation with dot-notation
    """

    def __init__(self, config: SchemaValidationConfig | None = None) -> None:
        """Initialize the schema validator.

        Args:
            config: Schema validation configuration with schemas and entity
                existence checker.
        """
        self._config = config or SchemaValidationConfig()

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
            return ValidationResult(
                is_valid=False,
                errors=["Data cannot be empty"],
                entity_id=operation.data.get("id") if operation.data else None,
            )

        entity_type = operation.entity_type
        schema = self._config.schemas.get(entity_type)

        if schema is None:
            return ValidationResult(
                is_valid=True,
                errors=[],
                entity_id=operation.data.get("id") if operation.data else None,
            )

        errors: list[str] = []
        data = operation.data

        for field_def in schema.fields:
            field_errors = self._validate_field(field_def, data, "")
            errors.extend(field_errors)

        entity_id = data.get("id") if data else None
        if entity_id is not None:
            entity_id = str(entity_id)
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            entity_id=entity_id,
        )

    def _validate_field(
        self,
        field_def: FieldDefinition,
        data: dict[str, Any],
        path_prefix: str,
    ) -> list[str]:
        """Validate a single field against its definition.

        Args:
            field_def: The field definition to validate against.
            data: The data to validate.
            path_prefix: Dot-notation path prefix for nested fields.

        Returns:
            List of error messages.
        """
        errors: list[str] = []
        field_path = (
            f"{path_prefix}.{field_def.name}" if path_prefix else field_def.name
        )

        ref_config = field_def.references
        is_entity_reference = ref_config is not None and "entity_type" in ref_config

        if is_entity_reference:
            return self._validate_reference(field_def, data, field_path)

        value = data.get(field_def.name)

        if field_def.required and value is None:
            errors.append(f"Field '{field_path}' is required")
            return errors

        if value is None:
            return errors

        type_errors = self._validate_type(field_def, value, field_path)
        errors.extend(type_errors)

        if not type_errors and field_def.type == "enum":
            enum_values = ref_config.get("values", []) if ref_config else []
            if enum_values and value not in enum_values:
                values_str = ", ".join(str(v) for v in enum_values)
                errors.append(
                    f"Invalid enum value '{value}' for field '{field_path}'. Expected one of [{values_str}]"
                )

        return errors

    def _validate_type(
        self,
        field_def: FieldDefinition,
        value: Any,
        field_path: str,
    ) -> list[str]:
        """Validate the type of a field value.

        Args:
            field_def: The field definition.
            value: The value to validate.
            field_path: The dot-notation path to the field.

        Returns:
            List of error messages.
        """
        field_type = field_def.type

        if field_type == "string":
            if not isinstance(value, str):
                return [f"Expected string type for field '{field_path}'"]

        elif field_type in ("integer", "float"):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                type_name = "number" if field_type == "float" else "integer"
                return [f"Expected {type_name} type for field '{field_path}'"]

        elif field_type == "boolean":
            if not isinstance(value, bool):
                return [f"Expected boolean type for field '{field_path}'"]

        elif field_type in ("date", "datetime"):
            if isinstance(value, str):
                if not TIMESTAMP_PATTERN.match(value):
                    return [
                        f"Expected ISO 8601 timestamp format for field '{field_path}'"
                    ]
            else:
                return [f"Expected ISO 8601 timestamp format for field '{field_path}'"]

        elif field_type in ("list", "dict"):
            expected_type = "array" if field_type == "list" else "object"
            if field_type == "list" and not isinstance(value, list):
                return [f"Expected {expected_type} type for field '{field_path}'"]
            if field_type == "dict" and not isinstance(value, dict):
                return [f"Expected {expected_type} type for field '{field_path}'"]

        return []

    def _validate_reference(
        self,
        field_def: FieldDefinition,
        data: dict[str, Any],
        field_path: str,
    ) -> list[str]:
        """Validate a reference field.

        Args:
            field_def: The field definition with reference info.
            data: The data to validate.
            field_path: The dot-notation path to the field.

        Returns:
            List of error messages.
        """
        errors: list[str] = []
        value = data.get(field_def.name)

        if value is None:
            if field_def.required:
                errors.append(f"Field '{field_path}' is required")
            return errors

        ref_config = field_def.references or {}
        ref_entity_type = ref_config.get("entity_type")

        if ref_entity_type and self._config.entity_exists_fn is not None:
            if isinstance(value, dict):
                ref_id = value.get("id")
                if ref_id is not None:
                    if not self._config.entity_exists_fn(ref_entity_type, ref_id):
                        errors.append(
                            f"Reference to non-existent entity '{ref_entity_type}' in field '{field_path}'"
                        )
            elif isinstance(value, str):
                if not self._config.entity_exists_fn(ref_entity_type, value):
                    errors.append(
                        f"Reference to non-existent entity '{ref_entity_type}' with ID '{value}'"
                    )

        return errors
