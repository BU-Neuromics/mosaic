"""Smoke tests for MosaicTUIApp — requires textual[dev] installed."""

from __future__ import annotations

import asyncio

import pytest

# Skip entire module if textual is not installed
textual = pytest.importorskip(
    "textual", reason="textual not installed; run: pip install datahelix-mosaic[tui]"
)

from mosaic.tui.backend.protocol import (
    EntityDetail,
    EntityTypeSummary,
    PagedResult,
    ProvenanceEvent,
    SchemaView,
)


# ---------------------------------------------------------------------------
# Minimal MockBackend for TUI tests
# ---------------------------------------------------------------------------


class MockBackend:
    def __init__(self, entity_types=None):
        self._entity_types = entity_types or [
            EntityTypeSummary(name="Sample", count=5),
            EntityTypeSummary(name="Donor", count=3),
        ]

    async def list_entity_types(self):
        return self._entity_types

    async def list_entities(self, entity_type, page=1, filter_text=""):
        return PagedResult(items=[], page=1, total_pages=1, total_items=0)

    async def get_entity(self, entity_type, entity_id):
        return EntityDetail(
            id=entity_id, entity_type=entity_type, fields={}, relationships=[]
        )

    async def get_schema(self):
        return SchemaView()

    async def get_provenance(self, entity_type, entity_id):
        return []


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


def test_app_mounts_with_mock_backend():
    """MosaicTUIApp can be created with a MockBackend without error."""
    from mosaic.tui.app import MosaicTUIApp

    backend = MockBackend()
    app = MosaicTUIApp(backend=backend)
    assert app is not None


def test_schema_cache_starts_empty():
    """Schema cache is None before on_mount is called."""
    from mosaic.tui.app import MosaicTUIApp

    backend = MockBackend()
    app = MosaicTUIApp(backend=backend)
    assert app.schema_cache is None


def test_get_or_fetch_schema_populates_cache():
    """get_or_fetch_schema populates the schema cache."""
    from mosaic.tui.app import MosaicTUIApp

    backend = MockBackend()
    app = MosaicTUIApp(backend=backend)

    schema = asyncio.run(app.get_or_fetch_schema())
    assert app.schema_cache is schema


def test_invalidate_schema_cache_refetches():
    """invalidate_schema_cache clears and re-fetches."""
    from mosaic.tui.app import MosaicTUIApp

    backend = MockBackend()
    app = MosaicTUIApp(backend=backend)

    schema1 = asyncio.run(app.get_or_fetch_schema())
    schema2 = asyncio.run(app.invalidate_schema_cache())
    # After invalidation, a new schema object is returned
    assert schema2 is not schema1


def test_app_pilot_smoke():
    """Textual pilot: app starts and exits cleanly."""
    from mosaic.tui.app import MosaicTUIApp

    backend = MockBackend()
    app = MosaicTUIApp(backend=backend)

    async def run():
        async with app.run_test(headless=True, size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.press("q")

    asyncio.run(run())
