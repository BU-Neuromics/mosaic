"""Schema validator for Hippo write operations backed by ``linkml.validator``.

Structural checks (required fields, type coercion, enum values, closed-schema
rejection) are delegated to ``SchemaRegistry.validate`` which wraps
``linkml.validator.Validator`` with ``JsonschemaValidationPlugin(closed=True)``.
Reference-existence checks (does the referenced entity exist in the database?)
remain here because they are a storage-level concern, not a schema concern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from hippo.core.validation.validators import (
    ValidationResult,
    WriteOperation,
    WriteValidator,
)
from hippo.linkml_bridge import SchemaRegistry


@dataclass
class SchemaValidationConfig:
    """Configuration for :class:`SchemaValidator`.

    Attributes:
        registry: LinkML-backed schema registry to validate against. If
            ``None``, validation is a no-op (pass-through).
        entity_exists_fn: Optional callable ``(entity_type, entity_id) -> bool``
            used for reference existence checks. When ``None``, reference
            checks are skipped.
    """

    registry: Optional[SchemaRegistry] = None
    entity_exists_fn: Optional[Callable[[str, str], bool]] = None


class SchemaValidator(WriteValidator):
    """Validate write operations against the LinkML-backed schema."""

    def __init__(self, config: Optional[SchemaValidationConfig] = None) -> None:
        self._config = config or SchemaValidationConfig()

    @property
    def priority(self) -> int:
        return 5

    def validate(self, operation: WriteOperation) -> ValidationResult:
        data = operation.data or {}
        entity_id = str(data["id"]) if "id" in data else None

        if not data:
            return ValidationResult(
                is_valid=False, errors=["Data cannot be empty"], entity_id=entity_id
            )

        registry = self._config.registry
        if registry is None or not registry.has_class(operation.entity_type):
            # No schema for this type → treat as pass-through.
            return ValidationResult(is_valid=True, errors=[], entity_id=entity_id)

        errors = list(registry.validate(data, operation.entity_type))

        # Reference-existence checks: require DB access, so they live outside
        # the LinkML validator. For each slot whose range is another class,
        # check that the referenced entity exists (if we have a way to).
        check = self._config.entity_exists_fn
        if check is not None:
            for slot_name, target_class in registry.reference_slots(
                operation.entity_type
            ):
                value = data.get(slot_name)
                if value is None:
                    continue
                ref_id = value.get("id") if isinstance(value, dict) else value
                if not isinstance(ref_id, str):
                    continue
                if not check(target_class, ref_id):
                    errors.append(
                        f"Reference to non-existent entity '{target_class}' "
                        f"with ID '{ref_id}' in field '{slot_name}'"
                    )

        return ValidationResult(
            is_valid=len(errors) == 0, errors=errors, entity_id=entity_id
        )
