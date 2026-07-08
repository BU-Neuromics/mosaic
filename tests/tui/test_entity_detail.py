"""Tests for EntityDetailScreen — fields, relationships, and action wiring."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip(
    "textual", reason="textual not installed; run: pip install datahelix-mosaic[tui]"
)

from textual.widgets import DataTable, Input, ListView, Select

from mosaic.tui.views.entity_detail import EntityDetailScreen


def _sample_id(backend) -> str:
    return next(iter(backend.entities["Sample"]))


async def _open_detail(app, pilot, entity_type: str, entity_id: str):
    app.open_entity_detail(entity_type, entity_id)
    await app.workers.wait_for_complete()
    await pilot.pause()
    screen = app.screen
    assert isinstance(screen, EntityDetailScreen)
    return screen


def test_detail_shows_fields_relationships_and_provenance(seeded_fake_backend):
    from mosaic.tui.app import MosaicTUIApp

    backend = seeded_fake_backend
    sample_id = _sample_id(backend)
    app = MosaicTUIApp(backend=backend)

    async def run():
        async with app.run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause()
            screen = await _open_detail(app, pilot, "Sample", sample_id)

            # System + temporal fields and user slots all land in the table.
            table = screen.query_one("#fields-table", DataTable)
            detail = await backend.get_entity("Sample", sample_id)
            assert table.row_count == len(detail.fields)

            # One outbound relationship: project_id → Project.
            rel_list = screen.query_one("#rel-list", ListView)
            assert len(rel_list) == 1

            # Provenance preview shows the create event.
            prov_list = screen.query_one("#prov-list", ListView)
            assert len(prov_list) == 1

    asyncio.run(run())


def test_detail_relationship_navigation_chains_screens(seeded_fake_backend):
    from mosaic.tui.app import MosaicTUIApp

    backend = seeded_fake_backend
    sample_id = _sample_id(backend)
    app = MosaicTUIApp(backend=backend)

    async def run():
        async with app.run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_detail(app, pilot, "Sample", sample_id)

            rel_list = app.screen.query_one("#rel-list", ListView)
            rel_list.focus()
            if rel_list.index is None:
                await pilot.press("down")
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()

            screen = app.screen
            assert isinstance(screen, EntityDetailScreen)
            assert screen._entity_type == "Project"

            # Escape unwinds one screen at a time.
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, EntityDetailScreen)
            assert app.screen._entity_type == "Sample"

    asyncio.run(run())


def test_detail_availability_action_writes_through_backend(seeded_fake_backend):
    from mosaic.tui.app import MosaicTUIApp
    from mosaic.tui.widgets.availability_dialog import AvailabilityScreen

    backend = seeded_fake_backend
    sample_id = _sample_id(backend)
    app = MosaicTUIApp(backend=backend)

    async def run():
        async with app.run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_detail(app, pilot, "Sample", sample_id)

            await pilot.press("a")
            await pilot.pause()
            dialog = app.screen
            assert isinstance(dialog, AvailabilityScreen)

            dialog.query_one("#status-select", Select).value = "distributed"
            dialog.query_one("#reason-input", Input).value = "sent to lab B"
            dialog._apply()
            await app.workers.wait_for_complete()
            await pilot.pause()

    asyncio.run(run())
    calls = [c for c in backend.calls if c[0] == "set_availability"]
    assert calls == [
        ("set_availability", ("Sample", sample_id, False, "distributed: sent to lab B"))
    ]
    assert backend.entities["Sample"][sample_id]["is_available"] is False


def test_detail_edit_action_opens_prefilled_form(seeded_fake_backend):
    from mosaic.tui.app import MosaicTUIApp
    from mosaic.tui.views.entity_form import EntityFormScreen

    backend = seeded_fake_backend
    sample_id = _sample_id(backend)
    app = MosaicTUIApp(backend=backend)

    async def run():
        async with app.run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_detail(app, pilot, "Sample", sample_id)

            await pilot.press("e")
            await pilot.pause()
            form = app.screen
            assert isinstance(form, EntityFormScreen)
            assert form.is_edit
            assert form.query_one("#field-name", Input).value == "S1"
            await pilot.press("escape")
            await pilot.pause()

    asyncio.run(run())


def test_detail_provenance_action_opens_history(seeded_fake_backend):
    from mosaic.tui.app import MosaicTUIApp
    from mosaic.tui.views.provenance import ProvenanceScreen

    backend = seeded_fake_backend
    sample_id = _sample_id(backend)
    app = MosaicTUIApp(backend=backend)

    async def run():
        async with app.run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_detail(app, pilot, "Sample", sample_id)

            await pilot.press("p")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert isinstance(app.screen, ProvenanceScreen)

    asyncio.run(run())


def test_detail_missing_entity_reports_error(seeded_fake_backend):
    from mosaic.tui.app import MosaicTUIApp
    from mosaic.tui.widgets.status_bar import StatusBar

    app = MosaicTUIApp(backend=seeded_fake_backend)

    async def run():
        async with app.run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause()
            app.open_entity_detail("Sample", "no-such-id")
            await app.workers.wait_for_complete()
            await pilot.pause()

            screen = app.screen
            assert isinstance(screen, EntityDetailScreen)
            assert screen._entity is None
            # The status bar lives on the base screen, not the pushed one.
            status_bar = app.screen_stack[0].query_one(StatusBar)
            assert "no-such-id" in status_bar._error_message

    asyncio.run(run())
