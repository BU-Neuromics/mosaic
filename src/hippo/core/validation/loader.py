"""Validator loading utilities for Hippo.

Provides functions to load and parse validators from validators.yaml files.
"""

import logging
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

from hippo.core.validation.executor import (
    ExecutorConfig,
    ValidatorConfig,
    ValidatorConfigError,
)

logger = logging.getLogger(__name__)


def expand_nested_rules(validator_config: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand nested rules within a validator configuration.

    Args:
        validator_config: The validator configuration with potential nested rules.

    Returns:
        List of expanded validator configurations.
    """
    expand_rules = validator_config.get("expand", [])

    if not expand_rules:
        return [validator_config]

    expanded = []
    for expand_rule in expand_rules:
        if not isinstance(expand_rule, dict):
            continue

        base_config = dict(validator_config)
        base_config.pop("expand", None)

        expanded_rule = {**base_config}

        for key, value in expand_rule.items():
            expanded_rule[key] = value

        nested_name = expanded_rule.get("name")
        if nested_name:
            expanded.append(expanded_rule)

    return expanded


def load_validators(
    validators_path: str,
    executor_config: Optional[ExecutorConfig] = None,
    feature_resolver: Optional[Callable[[str], bool]] = None,
) -> tuple[list[ValidatorConfig], list[ValidatorConfig], list[dict[str, Any]]]:
    """Load validators from validators.yaml file.

    Args:
        validators_path: Path to validators.yaml file.
        executor_config: Optional executor configuration.
        feature_resolver: Optional feature resolver function.

    Returns:
        Tuple of (valid_configs, invalid_configs, expanded_rules).
    """
    path = Path(validators_path)

    if not path.exists():
        logger.warning(f"Validators file not found: {validators_path}")
        return [], [], []

    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        logger.error(f"Invalid YAML in validators file: {e}")
        return [], [], []

    if not isinstance(data, dict):
        logger.error("Validators file must be a dictionary")
        return [], [], []

    if "validators" not in data:
        logger.warning("Missing 'validators' key in validators file")
        return [], [], []

    validators = data.get("validators", [])
    if not isinstance(validators, list):
        logger.error("'validators' must be a list")
        return [], [], []

    valid_configs: list[ValidatorConfig] = []
    invalid_configs: list[ValidatorConfig] = []
    expanded_rules: list[dict[str, Any]] = []

    for idx, validator in enumerate(validators):
        if not isinstance(validator, dict):
            logger.warning(f"Validator at index {idx} must be a dictionary")
            invalid_configs.append(
                ValidatorConfig(name=f"invalid_{idx}", enabled=False)
            )
            continue

        try:
            expanded = expand_nested_rules(validator)

            for expanded_rule in expanded:
                config = _parse_validator_config(expanded_rule, idx)

                if config.enabled:
                    valid_configs.append(config)
                    expanded_rules.append(expanded_rule)
                else:
                    logger.info(f"Validator {config.name} is disabled")

        except ValidatorConfigError as e:
            logger.warning(f"Invalid validator config at index {idx}: {e}")
            invalid_configs.append(
                ValidatorConfig(
                    name=validator.get("name", f"validator_{idx}"),
                    enabled=False,
                )
            )

    return valid_configs, invalid_configs, expanded_rules


def _parse_validator_config(
    config_dict: dict[str, Any],
    index: int,
) -> ValidatorConfig:
    """Parse and validate a validator configuration.

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


def create_executor_from_yaml(
    validators_path: str,
    executor_config: Optional[ExecutorConfig] = None,
    feature_resolver: Optional[Callable[[str], bool]] = None,
    validator_factory: Optional[Callable[[ValidatorConfig], Any]] = None,
) -> tuple[Any, list[ValidatorConfig], list[ValidatorConfig]]:
    """Create a ValidatorExecutor from a validators.yaml file.

    Args:
        validators_path: Path to validators.yaml file.
        executor_config: Optional executor configuration.
        feature_resolver: Optional feature resolver function.
        validator_factory: Optional factory to create validators from config.

    Returns:
        Tuple of (executor, valid_configs, invalid_configs).
    """
    valid_configs, invalid_configs, _ = load_validators(
        validators_path, executor_config, feature_resolver
    )

    executor = ExecutorConfig() if executor_config is None else executor_config

    from hippo.core.validation.executor import ValidatorExecutor

    exec_instance = ValidatorExecutor(
        config=executor if isinstance(executor, ExecutorConfig) else None,
        feature_resolver=feature_resolver,
    )

    for config in valid_configs:
        if validator_factory:
            validator = validator_factory(config)
            if validator:
                exec_instance.add_validator(validator, config)

    return exec_instance, valid_configs, invalid_configs
