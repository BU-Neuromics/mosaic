"""Every entry point Mosaic declares must import and resolve.

The ``mosaic.*`` entry-point groups are the public plugin seams (sec2):
external packages discover adapters, validators, and schema packages
through them. A dangling entry point is invisible until a consumer
tries to load it, so resolve them all here.

Per ADR-0004 (Hippo -> Mosaic rename), the entry-point groups are
**dual-registered** during the deprecation window: the canonical
``mosaic.*`` groups plus legacy ``hippo.*`` spellings that resolve the
same targets, so that Canon/Cappella and any third-party
``hippo-reference-*`` / ``hippo-adapter-*`` plugins keep working until
they migrate. We assert both sides of that contract here: every
``mosaic.*`` entry point resolves, and every legacy ``hippo.*`` entry
point resolves too (to the same target).
"""

from importlib.metadata import entry_points

import pytest

GROUP_SUFFIXES = [
    "storage_adapters",
    "write_validators",
    "schema_packages",
    "reference_loaders",
    "reference_loader_cli",
]

MOSAIC_GROUPS = [f"mosaic.{suffix}" for suffix in GROUP_SUFFIXES]
HIPPO_GROUPS = [f"hippo.{suffix}" for suffix in GROUP_SUFFIXES]


def _own_entry_points(groups: list) -> list:
    eps = []
    for group in groups:
        for ep in entry_points(group=group):
            # Only check entry points shipped by this package — an
            # unrelated broken third-party plugin must not fail Mosaic's
            # suite.
            if ep.value.startswith("mosaic."):
                eps.append(pytest.param(ep, id=f"{group}:{ep.name}"))
    return eps


def _load_or_skip(ep) -> None:
    try:
        assert ep.load() is not None
    except ImportError as exc:
        # A dangling entry point — its own ``mosaic.*`` target module missing —
        # is exactly the bug this guards (e.g. the stale sqlite adapter path
        # fixed in #43), so let that fail. But an adapter whose module imports
        # an *optional* third-party dependency (e.g. psycopg for postgres) is
        # legitimately unresolvable when that extra isn't installed (CI's bare
        # `.[dev]` job) — skip rather than fail.
        missing = getattr(exc, "name", "") or ""
        if "psycopg" in missing or "psycopg" in str(exc):
            pytest.skip(f"optional dependency not installed: {exc}")
        raise


@pytest.mark.parametrize("ep", _own_entry_points(MOSAIC_GROUPS))
def test_mosaic_entry_point_resolves(ep) -> None:
    """Every entry point declared under the canonical ``mosaic.*`` groups loads."""
    _load_or_skip(ep)


@pytest.mark.parametrize("ep", _own_entry_points(HIPPO_GROUPS))
def test_legacy_hippo_entry_point_resolves(ep) -> None:
    """Legacy ``hippo.*`` groups still resolve during the ADR-0004 deprecation window."""
    _load_or_skip(ep)


@pytest.mark.parametrize("suffix", GROUP_SUFFIXES)
def test_legacy_hippo_groups_mirror_mosaic_groups(suffix: str) -> None:
    """The legacy ``hippo.*`` group must dual-register the same names/targets

    as its canonical ``mosaic.*`` counterpart — that equivalence is the
    deprecation-window contract (ADR-0004): a consumer registered against
    either spelling must get the same plugin.
    """
    mosaic_eps = {ep.name: ep.value for ep in entry_points(group=f"mosaic.{suffix}")}
    hippo_eps = {ep.name: ep.value for ep in entry_points(group=f"hippo.{suffix}")}
    assert mosaic_eps, f"mosaic.{suffix} declared no entry points"
    assert hippo_eps == mosaic_eps


def test_storage_adapter_group_declares_both_adapters() -> None:
    names = {ep.name for ep in entry_points(group="mosaic.storage_adapters")}
    assert {"sqlite", "postgres"} <= names


def test_legacy_storage_adapter_group_declares_both_adapters() -> None:
    names = {ep.name for ep in entry_points(group="hippo.storage_adapters")}
    assert {"sqlite", "postgres"} <= names
