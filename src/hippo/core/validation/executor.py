"""Validator execution module for Hippo.

Provides ValidatorExecutor for running validators with support for
timeout, context propagation, feature dependencies, and error handling.
"""

import logging
import threading
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from hippo.core.validation.validators import (
    ValidationResult,
    WriteOperation,
    WriteValidator,
)

logger = logging.getLogger(__name__)


@dataclass
class ValidatorContext:
    """Context for passing data between validators.

    Supports mutation - subsequent validators see updates from previous validators.
    For isolation, use copy() to create an independent context.
    """

    data: dict[str, Any]
    entity_id: Optional[str] = None
    entity_type: Optional[str] = None
    operation: Optional[str] = None
    _metadata: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from the context.

        Args:
            key: The key to retrieve.
            default: Default value if key not found.

        Returns:
            The value or default.
        """
        return self._metadata.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a value in the context.

        Args:
            key: The key to set.
            value: The value to store.
        """
        self._metadata[key] = value

    def update(self, data: dict[str, Any]) -> None:
        """Update context with additional data.

        Args:
            data: Dictionary to merge into metadata.
        """
        self._metadata.update(data)

    def copy(self) -> "ValidatorContext":
        """Create an isolated copy of this context.

        The data dictionary is deep copied to ensure isolation.

        Returns:
            A new ValidatorContext with copied data.
        """
        return ValidatorContext(
            data=deepcopy(self.data),
            entity_id=self.entity_id,
            entity_type=self.entity_type,
            operation=self.operation,
            _metadata=deepcopy(self._metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert context to dictionary for validator use.

        Returns:
            Dictionary with data and metadata merged.
        """
        result = dict(self.data)
        result.update(self._metadata)
        return result


class ValidationTimeoutError(Exception):
    """Raised when validator execution times out."""

    def __init__(
        self,
        message: str,
        validator_name: str,
        timeout_seconds: float,
    ):
        self.validator_name = validator_name
        self.timeout_seconds = timeout_seconds
        super().__init__(message)


class FeatureNotAvailableError(Exception):
    """Raised when a required feature dependency is not available."""

    def __init__(
        self,
        message: str,
        feature_name: str,
        reason: Optional[str] = None,
    ):
        self.feature_name = feature_name
        self.reason = reason
        super().__init__(message)


class ValidatorExecutionError(Exception):
    """Raised when validator execution fails."""

    def __init__(
        self,
        message: str,
        validator_name: str,
        original_error: Optional[Exception] = None,
    ):
        self.validator_name = validator_name
        self.original_error = original_error
        super().__init__(message)


class ValidatorConfigError(Exception):
    """Raised when validator configuration is invalid."""

    def __init__(
        self,
        message: str,
        validator_path: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        self.validator_path = validator_path
        self.details = details or {}
        super().__init__(message)


@dataclass
class ValidatorConfig:
    """Configuration for a single validator."""

    name: str
    enabled: bool = True
    timeout_seconds: Optional[float] = None
    features: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutorConfig:
    """Configuration for the ValidatorExecutor."""

    timeout_seconds: Optional[float] = None
    fail_fast: bool = True
    validate_config: bool = True
    enabled: bool = True


class ValidatorExecutor:
    """Executor for running validators with advanced features.

    Supports:
    - Timeout handling
    - Context propagation between validators
    - Feature dependency resolution
    - Configuration validation with warnings
    """

    def __init__(
        self,
        config: Optional[ExecutorConfig] = None,
        feature_resolver: Optional[Callable[[str], bool]] = None,
    ):
        """Initialize ValidatorExecutor.

        Args:
            config: Configuration for executor behavior.
            feature_resolver: Optional callable to resolve feature availability.
        """
        self._config = config or ExecutorConfig()
        self._feature_resolver = feature_resolver
        self._validators: list[tuple[WriteValidator, ValidatorConfig]] = []
        self._initialized = False

    def add_validator(
        self,
        validator: WriteValidator,
        config: Optional[ValidatorConfig] = None,
    ) -> None:
        """Add a validator to the execution chain.

        Args:
            validator: The validator to add.
            config: Optional configuration for the validator.
        """
        validator_config = config or ValidatorConfig(name=type(validator).__name__)
        self._validators.append((validator, validator_config))

    def load_from_config(
        self,
        validators_config: list[dict[str, Any]],
        validator_factory: Optional[
            Callable[[ValidatorConfig], Optional[WriteValidator]]
        ] = None,
    ) -> tuple[list[ValidatorConfig], list[ValidatorConfig]]:
        """Load validators from configuration.

        Args:
            validators_config: List of validator configurations.
            validator_factory: Optional factory to create validators from config.

        Returns:
            Tuple of (loaded_validators, invalid_configs).
        """
        loaded: list[ValidatorConfig] = []
        invalid: list[ValidatorConfig] = []

        for idx, config_dict in enumerate(validators_config):
            try:
                validator_config = self._parse_validator_config(config_dict, idx)
                if validator_config.enabled:
                    loaded.append(validator_config)
                    if validator_factory:
                        validator = validator_factory(validator_config)
                        if validator:
                            self.add_validator(validator, validator_config)
                else:
                    logger.info(f"Validator {validator_config.name} is disabled")
            except ValidatorConfigError as e:
                if self._config.validate_config:
                    logger.warning(f"Invalid validator config: {e}")
                invalid.append(
                    ValidatorConfig(
                        name=config_dict.get("name", f"validator_{idx}"),
                        enabled=False,
                    )
                )

        self._initialized = True
        return loaded, invalid

    def _parse_validator_config(
        self,
        config_dict: dict[str, Any],
        index: int,
    ) -> ValidatorConfig:
        """Parse and validate a single validator configuration.

        Args:
            config_dict: Raw configuration dictionary.
            index: Index in configuration list (for error reporting).

        Returns:
            Validated ValidatorConfig.

        Raises:
            ValidatorConfigError: If configuration is invalid.
        """
        if not isinstance(config_dict, dict):
            raise ValidatorConfigError(
                f"Validator at index {index} must be a dictionary",
                validator_path=f"validators[{index}]",
                details={"index": index},
            )

        name = config_dict.get("name")
        if not name:
            raise ValidatorConfigError(
                f"Validator at index {index} missing required 'name'",
                validator_path=f"validators[{index}].name",
                details={"index": index},
            )

        return ValidatorConfig(
            name=name,
            enabled=config_dict.get("enabled", True),
            timeout_seconds=config_dict.get("timeout_seconds"),
            features=config_dict.get("features", []),
            config=config_dict.get("config", {}),
        )

    def execute(
        self,
        operation: WriteOperation,
        context: Optional[ValidatorContext] = None,
    ) -> ValidationResult:
        """Execute all validators in sequence.

        Args:
            operation: The write operation to validate.
            context: Optional context to pass between validators.

        Returns:
            ValidationResult with aggregated success/failure.
        """
        if not self._config.enabled:
            return ValidationResult(is_valid=True, errors=[])

        if not self._validators:
            return ValidationResult(is_valid=True, errors=[])

        ctx = context or ValidatorContext(
            data=operation.data,
            entity_id=operation.data.get("id"),
            entity_type=operation.entity_type,
            operation=operation.operation,
        )

        all_errors: list[str] = []
        entity_id = ctx.entity_id

        for validator, validator_config in self._validators:
            if not validator_config.enabled:
                continue

            result = self._execute_single(validator, validator_config, operation, ctx)

            if not result.is_valid:
                if self._config.fail_fast:
                    return ValidationResult(
                        is_valid=False,
                        errors=result.errors,
                        entity_id=entity_id,
                    )
                all_errors.extend(result.errors)
                if entity_id is None and result.entity_id:
                    entity_id = result.entity_id

        return ValidationResult(
            is_valid=len(all_errors) == 0,
            errors=all_errors,
            entity_id=entity_id,
        )

    def _execute_single(
        self,
        validator: WriteValidator,
        config: ValidatorConfig,
        operation: WriteOperation,
        context: ValidatorContext,
    ) -> ValidationResult:
        """Execute a single validator with timeout and feature checks.

        Args:
            validator: The validator to execute.
            config: Validator configuration.
            operation: The write operation.
            context: Current context.

        Returns:
            ValidationResult from the validator.
        """
        self._check_feature_dependencies(config)

        timeout = config.timeout_seconds or self._config.timeout_seconds

        if timeout:
            return self._execute_with_timeout(
                validator, config, operation, context, timeout
            )

        return self._execute_validator(validator, operation, context)

    def _execute_with_timeout(
        self,
        validator: WriteValidator,
        config: ValidatorConfig,
        operation: WriteOperation,
        context: ValidatorContext,
        timeout: float,
    ) -> ValidationResult:
        """Execute validator with timeout handling.

        Args:
            validator: The validator to execute.
            config: Validator configuration.
            operation: The write operation.
            context: Current context.
            timeout: Timeout in seconds.

        Returns:
            ValidationResult or timeout error.
        """
        result_container: list[ValidationResult] = []
        exception_container: list[Exception] = []

        def run_validator():
            try:
                result = self._execute_validator(validator, operation, context)
                result_container.append(result)
            except Exception as e:
                exception_container.append(e)

        thread = threading.Thread(target=run_validator)
        thread.daemon = True
        thread.start()
        thread.join(timeout)

        if thread.is_alive():
            raise ValidationTimeoutError(
                f"Validator '{config.name}' timed out after {timeout} seconds",
                validator_name=config.name,
                timeout_seconds=timeout,
            )

        if exception_container:
            original = exception_container[0]
            raise ValidatorExecutionError(
                f"Validator '{config.name}' raised exception: {original}",
                validator_name=config.name,
                original_error=original,
            )

        return (
            result_container[0]
            if result_container
            else ValidationResult(is_valid=True, errors=[])
        )

    def _execute_validator(
        self,
        validator: WriteValidator,
        operation: WriteOperation,
        context: ValidatorContext,
    ) -> ValidationResult:
        """Execute a validator and update context.

        Args:
            validator: The validator to execute.
            operation: The write operation.
            context: Current context (will be mutated).

        Returns:
            ValidationResult from the validator.
        """
        operation_copy = WriteOperation(
            operation=operation.operation,
            entity_type=operation.entity_type,
            data=context.data,
        )

        return validator.validate(operation_copy)

    def _check_feature_dependencies(self, config: ValidatorConfig) -> None:
        """Check and initialize feature dependencies.

        Args:
            config: Validator configuration with feature requirements.

        Raises:
            FeatureNotAvailableError: If a required feature is not available.
        """
        if not config.features or not self._feature_resolver:
            return

        for feature in config.features:
            if not self._feature_resolver(feature):
                raise FeatureNotAvailableError(
                    f"Required feature '{feature}' is not available for validator '{config.name}'",
                    feature_name=feature,
                    reason="Feature resolver returned False",
                )

    def get_validator_count(self) -> int:
        """Get the number of registered validators.

        Returns:
            Count of validators.
        """
        return len(self._validators)

    def clear_validators(self) -> None:
        """Clear all registered validators."""
        self._validators.clear()
        self._initialized = False


def create_executor(
    validators_config: Optional[list[dict[str, Any]]] = None,
    config: Optional[ExecutorConfig] = None,
    feature_resolver: Optional[Callable[[str], bool]] = None,
    validator_factory: Optional[
        Callable[[ValidatorConfig], Optional[WriteValidator]]
    ] = None,
) -> tuple[ValidatorExecutor, list[ValidatorConfig], list[ValidatorConfig]]:
    """Create a configured ValidatorExecutor.

    Args:
        validators_config: Optional list of validator configurations.
        config: Optional executor configuration.
        feature_resolver: Optional feature resolver function.
        validator_factory: Optional factory for creating validators.

    Returns:
        Tuple of (executor, loaded_configs, invalid_configs).
    """
    executor = ValidatorExecutor(
        config=config,
        feature_resolver=feature_resolver,
    )

    loaded = []
    invalid = []

    if validators_config:
        loaded, invalid = executor.load_from_config(
            validators_config, validator_factory
        )

    return executor, loaded, invalid
