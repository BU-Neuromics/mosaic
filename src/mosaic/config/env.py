"""``MOSAIC_*`` / legacy ``HIPPO_*`` environment-variable helper (ADR-0004).

Single choke point for runtime environment lookups: readers ask for the
un-prefixed variable name and get ``MOSAIC_<name>`` when set, falling back
to the legacy ``HIPPO_<name>`` spelling with a one-time
``DeprecationWarning`` per variable.
"""

from __future__ import annotations

import os
import warnings
from typing import Optional

#: Legacy variables already warned about in this process (warn once per var).
_warned: set[str] = set()


def get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    """Return ``$MOSAIC_<name>``, falling back to ``$HIPPO_<name>``.

    ``name`` is the un-prefixed suffix (e.g. ``"CACHE_DIR"``). When only
    the legacy ``HIPPO_`` spelling is set, its value is returned and a
    ``DeprecationWarning`` naming both spellings is emitted once per
    variable per process.
    """
    new_key = f"MOSAIC_{name}"
    old_key = f"HIPPO_{name}"

    value = os.environ.get(new_key)
    if value is not None:
        return value

    legacy = os.environ.get(old_key)
    if legacy is not None:
        if old_key not in _warned:
            _warned.add(old_key)
            warnings.warn(
                f"{old_key} is deprecated; set {new_key} instead "
                "(the component was renamed to Mosaic, ADR-0004).",
                DeprecationWarning,
                stacklevel=3,
            )
        return legacy

    return default
