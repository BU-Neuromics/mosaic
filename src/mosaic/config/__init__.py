"""Mosaic runtime configuration.

Entity schemas live in LinkML YAML and are loaded via
``mosaic.linkml_bridge.SchemaRegistry``; this package only covers the top-level
``mosaic.yaml`` runtime settings (legacy ``hippo.yaml`` still honored —
ADR-0004).
"""

from .models import MosaicConfig, ValidatorDefinition
from .models import HippoConfig  # deprecated alias (ADR-0004)
from .loader import (
    CONFIG_FILENAMES,
    LEGACY_CONFIG_FILENAMES,
    find_config_file,
    load_mosaic_config,
    load_hippo_config,  # deprecated alias (ADR-0004)
)
from .env import get_env
from .core import (
    ConfigError,
    ValidationError,
    SchemaError,
    substitute_env_vars,
)

__all__ = [
    "MosaicConfig",
    "HippoConfig",  # deprecated alias (ADR-0004)
    "ValidatorDefinition",
    "ConfigError",
    "ValidationError",
    "SchemaError",
    "CONFIG_FILENAMES",
    "LEGACY_CONFIG_FILENAMES",
    "find_config_file",
    "get_env",
    "load_mosaic_config",
    "load_hippo_config",  # deprecated alias (ADR-0004)
    "substitute_env_vars",
]
