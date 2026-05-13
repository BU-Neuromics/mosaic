"""Pytest configuration for tests."""

import sys
from pathlib import Path
import pytest

src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


def _build_minimal_schema_registry():
    """Return a SchemaRegistry over the bundled ``hippo_core`` schema.

    Plain helper (not a fixture) so that adapter constructions inside
    legacy test fixtures — which take ``db_path`` but no
    ``minimal_schema_registry`` — can build a registry inline without
    rewriting every fixture signature. Adapter writes whose
    ``entity_type`` is not declared in ``hippo_core`` simply skip the
    per-class typed-table path and fall through to the legacy
    ``entities`` table.
    """
    from hippo.linkml_bridge import SchemaRegistry
    from linkml_runtime.utils.schemaview import SchemaView
    import importlib.resources

    hippo_core_path = importlib.resources.files("hippo.schemas").joinpath("hippo_core.yaml")
    schema_view = SchemaView(str(hippo_core_path))
    return SchemaRegistry(schema_view)


@pytest.fixture
def minimal_schema_registry():
    """Provide a minimal SchemaRegistry using the bundled hippo_core schema.

    This fixture is useful for adapter tests that need a SchemaRegistry
    but don't require a custom user schema.
    """
    return _build_minimal_schema_registry()
