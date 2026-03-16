"""CEL Validator Engine - Validation Context."""

from typing import Any, Dict, List, Optional, Tuple

from hippo.core.validators import coerce


class ValidationContext:
    """Constructs context for CEL expression evaluation.

    Provides a dict-like interface compatible with cel-python's standard
    context format. Merges entity data with optional external parameters.
    Supports:
    - Multiple entity maps with last-map-wins merge strategy
    - Type coercion between strings, numbers, and booleans
    - Default values for missing fields
    - Deep merging of nested objects
    """

    def __init__(
        self,
        entity_data: Optional[Dict[str, Any]] = None,
        existing_entity: Optional[Dict[str, Any]] = None,
        entity_maps: Optional[List[Dict[str, Any]]] = None,
        type_coercion_enabled: bool = False,
        default_values: Optional[Dict[str, Any]] = None,
        **extra_vars: Any,
    ):
        """Initialize validation context.

        Args:
            entity_data: The new/modified entity data.
            existing_entity: The existing entity data (for updates).
            entity_maps: List of entity maps to merge (later maps win).
            type_coercion_enabled: Enable type coercion during merging.
            default_values: Default values for missing fields.
            **extra_vars: Additional variables available in CEL expressions.
        """
        self._type_coercion_enabled = type_coercion_enabled
        self._default_values = default_values or {}
        self._coercion_warnings: List[str] = []

        if entity_maps is not None:
            merged = self._merge_maps(entity_maps)
            self._merged_context = merged
            self._context: Dict[str, Any] = {"entity": merged}
        else:
            self._merged_context: Dict[str, Any] = entity_data or {}
            self._context = {"entity": entity_data or {}}

        if existing_entity is not None:
            self._context["existing"] = existing_entity
        self._context.update(extra_vars)

    def _expand_dot_notation(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Expand dot-notation keys into nested dicts.

        Args:
            data: The data with potential dot-notation keys.

        Returns:
            Data with dot-notation keys expanded into nested dicts.
        """
        result: Dict[str, Any] = {}

        for key, value in data.items():
            if "." in key:
                parts = key.split(".")
                current = result
                for i, part in enumerate(parts[:-1]):
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                current[parts[-1]] = value
            else:
                result[key] = value

        for key, value in data.items():
            if "." not in key and isinstance(value, dict):
                result[key] = self._expand_dot_notation(value)

        return result

    def _merge_maps(self, maps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge multiple maps with last-map-wins for scalars.

        Args:
            maps: List of dictionaries to merge.

        Returns:
            Merged dictionary.
        """
        if not maps:
            return {}

        result: Dict[str, Any] = {}
        existing_keys: set = set()
        for i, map_data in enumerate(maps):
            expanded = self._expand_dot_notation(map_data)
            if self._type_coercion_enabled:
                prefer_string = i == 0 and len(maps) == 1
                coerce_numbers = True
                processed = self._apply_coercion_to_single_map(
                    expanded,
                    prefer_string=prefer_string,
                    coerce_numbers=coerce_numbers,
                    skip_keys=existing_keys,
                )
                if result:
                    result = self._deep_merge(result, processed)
                    result = self._apply_coercion_to_map(result, processed)
                else:
                    result = processed
                existing_keys.update(expanded.keys())
            else:
                result = self._deep_merge(result, expanded)
                existing_keys.update(expanded.keys())

        return result

    def _apply_coercion_to_single_map(
        self,
        data: Dict[str, Any],
        prefer_string: bool = False,
        coerce_numbers: bool = True,
        skip_keys: set = None,
    ) -> Dict[str, Any]:
        """Apply type coercion to values in a single map.

        Args:
            data: The data dictionary.
            prefer_string: If True, convert numbers to strings before booleans.
            coerce_numbers: If True, convert numbers to boolean/string.
            skip_keys: Keys to skip coercion for (already handled in previous maps).

        Returns:
            Data with coerced values.
        """
        skip_keys = skip_keys or set()
        result = {}
        for key, value in data.items():
            if key in skip_keys:
                result[key] = value
                continue
            if isinstance(value, dict):
                result[key] = self._apply_coercion_to_single_map(
                    value, prefer_string, coerce_numbers, skip_keys
                )
            elif isinstance(value, str):
                num = coerce.coerce_to_number(value)
                if num is not None:
                    self._coercion_warnings.append(
                        f"Coerced '{value}' (string) to number {num}"
                    )
                    result[key] = num
                    continue
                bool_val = coerce.coerce_to_boolean(value)
                if bool_val is not None:
                    self._coercion_warnings.append(
                        f"Coerced '{value}' (string) to boolean {bool_val}"
                    )
                    result[key] = bool_val
                    continue
                result[key] = value
            elif isinstance(value, (int, float)) and coerce_numbers:
                if prefer_string:
                    str_val = coerce.coerce_to_string(value)
                    if str_val is not None:
                        self._coercion_warnings.append(
                            f"Coerced {value} (number) to string '{str_val}'"
                        )
                        result[key] = str_val
                        continue
                bool_val = coerce.coerce_to_boolean(value)
                if bool_val is not None:
                    self._coercion_warnings.append(
                        f"Coerced {value} (number) to boolean {bool_val}"
                    )
                    result[key] = bool_val
                    continue
                if prefer_string:
                    result[key] = value
                else:
                    str_val = coerce.coerce_to_string(value)
                    if str_val is not None:
                        self._coercion_warnings.append(
                            f"Coerced {value} (number) to string '{str_val}'"
                        )
                        result[key] = str_val
                        continue
                    result[key] = value
            else:
                result[key] = value
        return result

    def _apply_coercion_to_map(
        self, base: Dict[str, Any], override: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply type coercion when merging two maps.

        Args:
            base: The base map.
            override: The overriding map.

        Returns:
            Override map with coerced values for conflicting keys.
        """
        result = dict(base)
        result.update(override)
        for key in base:
            if key in override:
                base_type = coerce.get_value_type(base[key])
                override_type = coerce.get_value_type(override[key])
                if (
                    base_type != override_type
                    and base[key] is not None
                    and override[key] is not None
                ):
                    base_prec = coerce.get_type_precedence(base_type)
                    override_prec = coerce.get_type_precedence(override_type)
                    if override_prec > base_prec:
                        result[key] = override[key]
                    elif base_prec > override_prec:
                        coerced, warning = coerce.coerce_value(override[key], base_type)
                        if warning:
                            warning = warning.replace("Coerced", "Coerced for merge")
                            self._coercion_warnings.append(warning)
                        result[key] = coerced
        return result

    def _deep_merge(self, base: Any, override: Any) -> Any:
        """Recursively merge override into base.

        Last-map-wins for scalars, deep merge for dicts.

        Args:
            base: The base value.
            override: The overriding value.

        Returns:
            Merged result.
        """
        if not isinstance(base, dict) or not isinstance(override, dict):
            return override

        result = dict(base)
        for key, value in override.items():
            if key in result:
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    def to_dict(self) -> Dict[str, Any]:
        """Return the context as a dictionary.

        Returns:
            Dictionary suitable for CEL evaluation.
        """
        return self._context

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from the context.

        Args:
            key: The key to look up.
            default: Default value if key not found.

        Returns:
            The context value or default.
        """
        return self._context.get(key, default)

    def get_merged_context(self) -> Dict[str, Any]:
        """Return the merged entity context.

        Returns:
            The merged entity data dictionary.
        """
        return self._merged_context

    def get_field(self, path: str) -> Any:
        """Get a field from the merged context using dot-notation.

        Args:
            path: The dot-notation path (e.g., 'user.profile.name').

        Returns:
            The field value or None if not found.
        """
        return self.get_field_with_default(path)

    def get_field_with_default(self, path: str) -> Any:
        """Get a field from the merged context with default values support.

        Args:
            path: The dot-notation path (e.g., 'user.profile.name').

        Returns:
            The field value, default value, or None if not found.
        """
        parts = path.split(".")
        current = self._merged_context

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                if path in self._default_values:
                    return self._default_values[path]
                return None

        return current

    def get_coercion_warnings(self) -> List[str]:
        """Return list of coercion warnings.

        Returns:
            List of warning messages from type coercion events.
        """
        return list(self._coercion_warnings)

    def __getitem__(self, key: str) -> Any:
        """Allow dict-like access to context."""
        return self._context[key]

    def __setitem__(self, key: str, value: Any) -> None:
        """Allow dict-like setting of context values."""
        self._context[key] = value

    def __contains__(self, key: str) -> bool:
        """Check if key exists in context."""
        return key in self._context
