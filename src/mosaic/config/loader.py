"""Mosaic runtime-config loader.

Entity schemas are loaded via ``mosaic.linkml_bridge.SchemaRegistry.from_path``;
this module only handles the top-level ``mosaic.yaml`` runtime config
(legacy ``hippo.yaml`` is still honored — ADR-0004).
"""

import warnings
from pathlib import Path
from typing import Optional, Union

import yaml
from pydantic import ValidationError as PydanticValidationError

from .core import (
    ConfigError,
    ValidationError as ValidationErrorBase,
    substitute_env_vars,
)
from .models import MosaicConfig

#: Config filenames auto-detected in a directory, in priority order.
CONFIG_FILENAMES = ("config.json", "mosaic.yaml", "mosaic.yml")
#: Legacy filenames (ADR-0004) — still detected, with a DeprecationWarning.
LEGACY_CONFIG_FILENAMES = ("hippo.yaml", "hippo.yml")


def find_config_file(directory: Optional[Union[str, Path]] = None) -> Optional[Path]:
    """Return the runtime-config file in *directory* (default: the cwd).

    The single place the config filename convention lives (ADR-0004 /
    WP-H4): scans :data:`CONFIG_FILENAMES` first — so ``mosaic.yaml`` wins
    silently over a co-present ``hippo.yaml`` — then falls back to
    :data:`LEGACY_CONFIG_FILENAMES` with one ``DeprecationWarning`` naming
    the path that was found. Returns ``None`` when nothing matches.
    """
    base = Path(directory) if directory is not None else Path(".")
    for name in CONFIG_FILENAMES:
        candidate = base / name
        if candidate.exists():
            return candidate
    for name in LEGACY_CONFIG_FILENAMES:
        candidate = base / name
        if candidate.exists():
            warnings.warn(
                f"Found legacy config {candidate}; rename it to "
                "'mosaic.yaml' (the component was renamed to Mosaic, "
                "ADR-0004). The 'hippo.yaml' fallback will be removed in "
                "a future release.",
                DeprecationWarning,
                stacklevel=2,
            )
            return candidate
    return None


def load_mosaic_config(config_path: Union[str, Path]) -> MosaicConfig:
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
        return MosaicConfig(**substituted_config)
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


# Deprecated alias (ADR-0004): the loader was renamed with the component.
load_hippo_config = load_mosaic_config  # deprecated
