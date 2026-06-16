"""Every entry point Hippo declares must import and resolve.

The ``hippo.*`` entry-point groups are the public plugin seams (sec2):
external packages discover adapters, validators, and schema packages
through them. A dangling entry point is invisible until a consumer
tries to load it, so resolve them all here.
"""

from importlib.metadata import entry_points

import pytest

HIPPO_GROUPS = [
    "hippo.storage_adapters",
    "hippo.write_validators",
    "hippo.schema_packages",
    "hippo.reference_loaders",
    "hippo.reference_loader_cli",
]


def _hippo_entry_points() -> list:
    eps = []
    for group in HIPPO_GROUPS:
        for ep in entry_points(group=group):
            # Only check entry points shipped by this package — an
            # unrelated broken third-party plugin must not fail Hippo's
            # suite.
            if ep.value.startswith("hippo."):
                eps.append(pytest.param(ep, id=f"{group}:{ep.name}"))
    return eps


@pytest.mark.parametrize("ep", _hippo_entry_points())
def test_entry_point_resolves(ep) -> None:
    try:
        assert ep.load() is not None
    except ImportError as exc:
        # A dangling entry point — its own ``hippo.*`` target module missing —
        # is exactly the bug this guards (e.g. the stale sqlite adapter path
        # fixed in #43), so let that fail. But an adapter whose module imports
        # an *optional* third-party dependency (e.g. psycopg for postgres) is
        # legitimately unresolvable when that extra isn't installed (CI's bare
        # `.[dev]` job) — skip rather than fail.
        missing = getattr(exc, "name", "") or ""
        if "psycopg" in missing or "psycopg" in str(exc):
            pytest.skip(f"optional dependency not installed: {exc}")
        raise


def test_storage_adapter_group_declares_both_adapters() -> None:
    names = {ep.name for ep in entry_points(group="hippo.storage_adapters")}
    assert {"sqlite", "postgres"} <= names
