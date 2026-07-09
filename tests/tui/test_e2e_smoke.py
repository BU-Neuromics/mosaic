"""End-to-end smoke test — real app over a real SDKBackend + temp SQLite db."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

pytest.importorskip(
    "textual", reason="textual not installed; run: pip install datahelix-mosaic[tui]"
)

from mosaic.tui.backend.sdk import SDKBackend

_FIXTURE_SCHEMA = (
    Path(__file__).parents[1] / "fixtures" / "schemas" / "sample_schema.yaml"
)


@pytest.fixture
def sdk_backend(tmp_path):
    return SDKBackend(db_path=tmp_path / "smoke.db", schema_path=_FIXTURE_SCHEMA)


def test_app_boots_and_browses_real_database(sdk_backend):
    """Full stack: boot, sidebar load, browse entities, open detail."""
    from textual.widgets import DataTable

    from mosaic.tui.app import MosaicTUIApp
    from mosaic.tui.views.entity_browser import EntityBrowserView
    from mosaic.tui.views.entity_detail import EntityDetailScreen
    from mosaic.tui.widgets.sidebar import EntityTypeSidebar
    from mosaic.tui.widgets.status_bar import StatusBar

    app = MosaicTUIApp(backend=sdk_backend)

    async def run():
        # Seed real entities through the real SDK backend.
        project_id = await sdk_backend.create_entity(
            "Project", {"name": "Smoke", "description": "smoke project"}
        )
        sample_id = await sdk_backend.create_entity(
            "Sample",
            {"name": "SMK-1", "project_id": project_id, "status": "active"},
        )

        async with app.run_test(headless=True, size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Connection probe landed in the status bar.
            status_bar = app.query_one(StatusBar)
            assert status_bar._connection_ok is True
            assert status_bar._backend_mode == "sdk"

            # Sidebar lists the real schema's entity types.
            sidebar = app.query_one(EntityTypeSidebar)
            labels = " ".join(
                str(label.renderable) for label in sidebar.query("ListItem Label")
            )
            assert "Project" in labels and "Sample" in labels

            # Browse Samples and open the seeded entity's detail screen.
            await app.open_entity_browser("Sample")
            await app.workers.wait_for_complete()
            await pilot.pause()
            view = app.query_one(EntityBrowserView)
            table = view.query_one("#entity-table", DataTable)
            assert table.row_count == 1

            app.open_entity_detail("Sample", sample_id)
            await app.workers.wait_for_complete()
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, EntityDetailScreen)
            assert screen._entity is not None
            # Real computed temporal fields are present on the detail.
            assert screen._entity.fields.get("created_at")
            await pilot.press("escape")
            await pilot.pause()

    asyncio.run(run())
