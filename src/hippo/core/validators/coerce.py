"""Type coercion utilities for validation context."""

from typing import Any, Optional, Tuple


def coerce_to_number(value: Any) -> Optional[float]:
    """Coerce a value to a number (int or float).

    Args:
        value: The value to coerce.

    Returns:
        The coerced number, or None if coercion is not possible.
    """
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            return None
    return None


def coerce_to_boolean(value: Any) -> Optional[bool]:
    """Coerce a value to a boolean.

    Args:
        value: The value to coerce.

    Returns:
        The coerced boolean, or None if coercion is not possible.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lower = value.lower()
        if lower == "true":
            return True
        if lower == "false":
            return False
    return None


def coerce_to_string(value: Any) -> Optional[str]:
    """Coerce a value to a string.

    Args:
        value: The value to coerce.

    Returns:
        The coerced string, or None if coercion is not possible.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def get_type_precedence(value_type: str) -> int:
    """Get the precedence for a type.

    Higher precedence wins in type conflicts.

    Args:
        value_type: The type name ('string', 'number', 'boolean', 'null').

    Returns:
        Precedence value: string=4, number=3, boolean=2, null=1.
    """
    precedences = {
        "string": 4,
        "number": 3,
        "boolean": 2,
        "null": 1,
    }
    return precedences.get(value_type.lower(), 0)


def get_value_type(value: Any) -> str:
    """Get the type name for a value.

    Args:
        value: The value to check.

    Returns:
        Type name: 'string', 'number', 'boolean', 'null', or 'object'.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (list, tuple)):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def coerce_value(
    value: Any,
    target_type: str,
    source_path: str = "",
) -> Tuple[Any, Optional[str]]:
    """Coerce a value to a target type.

    Args:
        value: The value to coerce.
        target_type: The desired type ('string', 'number', 'boolean').
        source_path: Path for warning messages.

    Returns:
        Tuple of (coerced value, warning message or None).
    """
    warning = None
    original_type = get_value_type(value)

    if original_type == target_type:
        return value, warning

    if target_type == "number":
        result = coerce_to_number(value)
        if result is not None:
            warning = f"Coerced '{value}' ({original_type}) to number {result}"
            return result, warning
    elif target_type == "boolean":
        result = coerce_to_boolean(value)
        if result is not None:
            warning = f"Coerced '{value}' ({original_type}) to boolean {result}"
            return result, warning
    elif target_type == "string":
        result = coerce_to_string(value)
        if result is not None:
            warning = f"Coerced {original_type} value to string '{result}'"
            return result, warning

    return value, None
