"""Every ``hippo.*`` entry point Hippo itself declares must resolve.

A dangling entry point is invisible until a consumer tries to load it —
this is exactly the class of bug that left the ``sqlite`` storage adapter
pointing at a non-existent module until issue #43. Loading each declared
entry point catches that regression at test time instead.
"""

import importlib.util
from importlib.metadata import distribution

import pytest

_HIPPO_GROUP_PREFIX = "hippo."

# Entry points gated behind an optional install extra (see pyproject.toml
# [project.optional-dependencies]) — skipped rather than failed when the
# extra's underlying package isn't installed, since that's a legitimate
# "not installed here" rather than a dangling entry point.
_OPTIONAL_EXTRA_PACKAGE = {
    ("hippo.storage_adapters", "postgres"): "psycopg",
}


def _hippo_entry_points():
    dist = distribution("hippo")
    return [ep for ep in dist.entry_points if ep.group.startswith(_HIPPO_GROUP_PREFIX)]


@pytest.mark.parametrize(
    "entry_point",
    _hippo_entry_points(),
    ids=lambda ep: f"{ep.group}:{ep.name}",
)
def test_entry_point_resolves(entry_point):
    required_package = _OPTIONAL_EXTRA_PACKAGE.get((entry_point.group, entry_point.name))
    if required_package and importlib.util.find_spec(required_package) is None:
        pytest.skip(f"optional dependency {required_package!r} not installed")
    entry_point.load()


def test_at_least_one_entry_point_per_declared_group():
    declared_groups = {
        "hippo.storage_adapters",
        "hippo.write_validators",
        "hippo.schema_packages",
        "hippo.reference_loaders",
        "hippo.reference_loader_cli",
    }
    found_groups = {ep.group for ep in _hippo_entry_points()}
    assert declared_groups <= found_groups
