"""Tests for EntityTypeSidebar widget."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip(
    "textual", reason="textual not installed; run: pip install datahelix-mosaic[tui]"
)

from mosaic.tui.backend.protocol import EntityTypeSummary
from mosaic.tui.widgets.sidebar import EntityTypeSidebar, _SCHEMA_EXPLORER_LABEL


class MockBackend:
    def __init__(self, entity_types=None):
        self._entity_types = entity_types or [
            EntityTypeSummary(name="Sample", count=5),
            EntityTypeSummary(name="Donor", count=3),
        ]

    async def list_entity_types(self):
        return self._entity_types

    async def list_entities(self, *a, **kw):
        from mosaic.tui.backend.protocol import PagedResult

        return PagedResult(items=[], page=1, total_pages=1, total_items=0)

    async def get_entity(self, *a, **kw):
        from mosaic.tui.backend.protocol import EntityDetail

        return EntityDetail(id="x", entity_type="Sample", fields={}, relationships=[])

    async def get_schema(self):
        from mosaic.tui.backend.protocol import SchemaView

        return SchemaView()

    async def get_provenance(self, *a, **kw):
        return []


def test_schema_explorer_label_constant():
    """SCHEMA_EXPLORER_LABEL is the expected string."""
    assert _SCHEMA_EXPLORER_LABEL == "Schema Explorer"


def test_sidebar_entity_type_selected_message():
    """EntityTypeSidebar.EntityTypeSelected carries entity_type and count."""
    msg = EntityTypeSidebar.EntityTypeSelected("Sample", 42)
    assert msg.entity_type == "Sample"
    assert msg.entity_count == 42


def test_sidebar_schema_explorer_selected_message():
    """EntityTypeSidebar.SchemaExplorerSelected is instantiable."""
    msg = EntityTypeSidebar.SchemaExplorerSelected()
    assert msg is not None


def test_sidebar_pilot_schema_explorer_last():
    """Schema Explorer entry is the last item in the sidebar after loading."""
    from mosaic.tui.app import MosaicTUIApp

    backend = MockBackend()
    app = MosaicTUIApp(backend=backend)

    async def run():
        async with app.run_test(headless=True, size=(80, 24)) as pilot:
            await pilot.pause()
            sidebar = app.query_one(EntityTypeSidebar)
            items = list(sidebar.query("ListItem"))
            # Last item should be Schema Explorer
            last_item = items[-1]
            assert last_item.id == "schema-explorer-item"
            await pilot.press("q")

    asyncio.run(run())


def test_sidebar_pilot_entity_type_selection():
    """Selecting an entity type in the sidebar emits EntityTypeSelected."""
    from mosaic.tui.app import MosaicTUIApp

    backend = MockBackend()
    app = MosaicTUIApp(backend=backend)
    received: list = []

    async def run():
        async with app.run_test(headless=True, size=(80, 24)) as pilot:
            await pilot.pause()
            sidebar = app.query_one(EntityTypeSidebar)

            # Capture messages
            original_post = sidebar.post_message

            def capture(msg):
                received.append(msg)
                return original_post(msg)

            sidebar.post_message = capture

            # Select first entity type item
            items = list(sidebar.query("ListItem"))
            entity_items = [
                i
                for i in items
                if i.id not in ("schema-explorer-item", "query-item")
            ]
            assert entity_items, "sidebar should contain entity type items"
            sidebar.index = items.index(entity_items[0])
            sidebar.action_select_cursor()

            await pilot.pause()
            await pilot.press("q")

    asyncio.run(run())
    assert any(
        isinstance(msg, EntityTypeSidebar.EntityTypeSelected) for msg in received
    )
