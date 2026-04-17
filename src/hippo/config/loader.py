"""Hippo runtime-config loader.

Entity schemas are loaded via ``hippo.linkml_bridge.SchemaRegistry.from_path``;
this module only handles the top-level ``hippo.yaml`` runtime config.
"""

from pathlib import Path
from typing import Union

import yaml
from pydantic import ValidationError as PydanticValidationError

from .core import (
    ConfigError,
    ValidationError as ValidationErrorBase,
    substitute_env_vars,
)
from .models import HippoConfig


def load_hippo_config(config_path: Union[str, Path]) -> HippoConfig:
    config_path = Path(config_path)

    if not config_path.exists():
        raise ConfigError(f"Configuration file not found: {config_path}")

    try:
        with open(config_path) as f:
            raw_config = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"invalid YAML syntax: {e}")

    substituted_config = substitute_env_vars(raw_config)

    try:
        return HippoConfig(**substituted_config)
    except PydanticValidationError as e:
        errors = e.errors()
        if errors:
            first_error = errors[0]
            loc = ".".join(str(part) for part in first_error["loc"])
            msg = first_error["msg"]
            input_val = first_error.get("input")
            type_info = first_error.get("type", "unknown")
            if type_info == "missing":
                raise ConfigError(
                    f"Missing required field: '{loc}'",
                    field_name=loc,
                )
            raise ValidationErrorBase(
                f"Configuration validation failed for field '{loc}': {msg} "
                f"(expected {type_info}, got {input_val})",
                expected_type=type_info,
                actual_value=input_val,
            )
        raise ValidationErrorBase(
            "Configuration validation failed",
            expected_type=None,
            actual_value=None,
        )
