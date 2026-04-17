"""Hippo runtime configuration.

Entity schemas live in LinkML YAML and are loaded via
``hippo.linkml_bridge.SchemaRegistry``; this package only covers the top-level
``hippo.yaml`` runtime settings.
"""

from .models import HippoConfig, ValidatorDefinition
from .loader import load_hippo_config
from .core import (
    ConfigError,
    ValidationError,
    SchemaError,
    substitute_env_vars,
)

__all__ = [
    "HippoConfig",
    "ValidatorDefinition",
    "ConfigError",
    "ValidationError",
    "SchemaError",
    "load_hippo_config",
    "substitute_env_vars",
]
