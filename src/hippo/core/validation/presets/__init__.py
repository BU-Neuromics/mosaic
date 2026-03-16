"""Preset base classes and registry for Hippo validation presets."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from hippo.core.validation.validators import ValidationResult, WriteOperation


@dataclass
class PresetConfig:
    """Configuration for a preset validator.

    Attributes:
        preset_type: The type identifier of the preset.
        config: The preset-specific configuration dict.
    """

    preset_type: str
    config: dict[str, Any] = field(default_factory=dict)


class PresetValidator(ABC):
    """Abstract base class for preset validators.

    Presets are reusable validation logic that can be configured via
    YAML/JSON schema and applied to entity fields.
    """

    def __init__(self, config: PresetConfig | None = None) -> None:
        """Initialize the preset validator.

        Args:
            config: The preset configuration.
        """
        self._config = config or PresetConfig(preset_type=self.preset_type)

    @property
    @abstractmethod
    def preset_type(self) -> str:
        """Return the preset type identifier."""
        ...

    @property
    def priority(self) -> int:
        """Priority of the preset validator.

        Higher priority validators execute first.
        Defaults to 10 (higher than default WriteValidator).
        """
        return 10

    @abstractmethod
    def validate(self, operation: WriteOperation) -> ValidationResult:
        """Validate a write operation using this preset.

        Args:
            operation: The write operation to validate.

        Returns:
            ValidationResult indicating success or failure with errors.
        """
        ...

    def _get_field_value(
        self, data: dict[str, Any], field_path: str
    ) -> tuple[Any | None, str]:
        """Get a field value from data using dot-notation path.

        Args:
            data: The data dict to extract from.
            field_path: Dot-notation path to the field.

        Returns:
            Tuple of (value, actual_path_found).
        """
        if "." not in field_path:
            return data.get(field_path), field_path

        parts = field_path.split(".")
        current = data
        for part in parts[:-1]:
            if not isinstance(current, dict):
                return None, field_path
            current = current.get(part)
            if current is None:
                return None, field_path

        if isinstance(current, dict):
            return current.get(parts[-1]), field_path
        return None, field_path


class PresetRegistry:
    """Registry for built-in preset validators.

    Maintains a collection of preset validators that can be referenced
    by name in schema definitions.
    """

    def __init__(self) -> None:
        self._presets: dict[str, type[PresetValidator]] = {}

    def register(self, preset_type: str, preset_class: type[PresetValidator]) -> None:
        """Register a preset validator class.

        Args:
            preset_type: The unique type identifier for the preset.
            preset_class: The preset validator class.
        """
        self._presets[preset_type] = preset_class

    def get(self, preset_type: str) -> type[PresetValidator] | None:
        """Get a preset validator class by type.

        Args:
            preset_type: The preset type identifier.

        Returns:
            The preset validator class, or None if not found.
        """
        return self._presets.get(preset_type)

    def create(
        self, preset_type: str, config: dict[str, Any]
    ) -> PresetValidator | None:
        """Create a preset validator instance.

        Args:
            preset_type: The preset type identifier.
            config: The preset configuration.

        Returns:
            A preset validator instance, or None if not found.
        """
        preset_class = self.get(preset_type)
        if preset_class is None:
            return None
        return preset_class(PresetConfig(preset_type=preset_type, config=config))

    def list_presets(self) -> list[str]:
        """List all registered preset types.

        Returns:
            List of preset type identifiers.
        """
        return list(self._presets.keys())


_builtin_preset_registry = PresetRegistry()


def get_preset_registry() -> PresetRegistry:
    """Get the global preset registry.

    Returns:
        The global PresetRegistry instance.
    """
    return _builtin_preset_registry


from hippo.core.validation.presets.errors import (
    CountConstraintViolation,
    ErrorMessageBuilder,
    FieldRequiredViolation,
    ImmutableFieldViolation,
    ReferenceConstraintViolation,
    SelfReferenceViolation,
)
from hippo.core.validation.presets.builtins import (
    COUNT_CONSTRAINT_PRESET,
    FIELD_REQUIRED_IF_PRESET,
    IMMUTABLE_FIELD_PRESET,
    NO_SELF_REF_PRESET,
    REF_CHECK_PRESET,
    CountConstraintPreset,
    FieldRequiredIfPreset,
    ImmutableFieldPreset,
    NoSelfRefPreset,
    RefCheckPreset,
    register_presets,
)

__all__ = [
    "PresetConfig",
    "PresetValidator",
    "PresetRegistry",
    "get_preset_registry",
    "ErrorMessageBuilder",
    "ReferenceConstraintViolation",
    "CountConstraintViolation",
    "ImmutableFieldViolation",
    "FieldRequiredViolation",
    "SelfReferenceViolation",
    "REF_CHECK_PRESET",
    "COUNT_CONSTRAINT_PRESET",
    "IMMUTABLE_FIELD_PRESET",
    "FIELD_REQUIRED_IF_PRESET",
    "NO_SELF_REF_PRESET",
    "RefCheckPreset",
    "CountConstraintPreset",
    "ImmutableFieldPreset",
    "FieldRequiredIfPreset",
    "NoSelfRefPreset",
    "register_presets",
]
