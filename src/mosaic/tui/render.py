"""Small formatting helpers shared by TUI views."""

from __future__ import annotations

from typing import Any

#: Maximum characters shown for a cell value before truncation.
MAX_CELL_LEN = 40


def short_id(entity_id: Any, length: int = 8) -> str:
    """Return a truncated id with an ellipsis when shortened."""
    text = str(entity_id)
    return f"{text[:length]}…" if len(text) > length else text


def format_timestamp(timestamp: Any) -> str:
    """Render an ISO timestamp as ``YYYY-MM-DD HH:MM:SS``."""
    text = str(timestamp or "")
    return text[:19].replace("T", " ") if text else ""


def format_value(value: Any, max_len: int = MAX_CELL_LEN) -> str:
    """Render an arbitrary field value as a single-line cell string."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        text = ", ".join(format_value(v, max_len) for v in value)
    else:
        text = str(value)
    text = text.replace("\n", " ")
    return f"{text[: max_len - 1]}…" if len(text) > max_len else text
