"""Tests for ProvenanceScreen — full history table and payload inspector."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip(
    "textual", reason="textual not installed; run: pip install datahelix-mosaic[tui]"
)

from textual.widgets import DataTable

from mosaic.tui.views.provenance import ProvenanceScreen


def _sample_id(backend) -> str:
    return next(iter(backend.entities["Sample"]))


async def _push_provenance(app, pilot, backend, entity_id: str) -> ProvenanceScreen:
    screen = ProvenanceScreen(
        backend=backend, entity_type="Sample", entity_id=entity_id
    )
    await app.push_screen(screen)
    await app.workers.wait_for_complete()
    await pilot.pause()
    return screen


def test_provenance_lists_events_newest_first(seeded_fake_backend):
    from mosaic.tui.app import MosaicTUIApp

    backend = seeded_fake_backend
    sample_id = _sample_id(backend)
    app = MosaicTUIApp(backend=backend)

    async def run():
        async with app.run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause()
            # Add a second (newer) event before opening the screen.
            await backend.update_entity(
                "Sample", sample_id, {"name": "S1", "volume_ml": 2.0}
            )
            screen = await _push_provenance(app, pilot, backend, sample_id)

            table = screen.query_one("#provenance-table", DataTable)
            assert table.row_count == 2
            # Newest first: row 0 is the update (event #2), row 1 the create.
            assert screen._events[0].event_type == "update"
            assert screen._events[1].event_type == "create"
            first_row = table.get_row_at(0)
            assert first_row[0] == "2"
            assert first_row[2] == "update"
            assert not screen.has_class("empty")

    asyncio.run(run())


def test_provenance_payload_follows_highlight(seeded_fake_backend):
    from mosaic.tui.app import MosaicTUIApp

    backend = seeded_fake_backend
    sample_id = _sample_id(backend)
    app = MosaicTUIApp(backend=backend)
    shown: list[int] = []

    async def run():
        async with app.run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause()
            await backend.update_entity(
                "Sample", sample_id, {"name": "S1", "volume_ml": 2.0}
            )
            screen = await _push_provenance(app, pilot, backend, sample_id)
            screen._show_event = shown.append  # record selections

            table = screen.query_one("#provenance-table", DataTable)
            table.focus()
            await pilot.press("down")
            await pilot.pause()

    asyncio.run(run())
    assert shown and shown[-1] == 1


def test_provenance_empty_state(seeded_fake_backend):
    from mosaic.tui.app import MosaicTUIApp

    backend = seeded_fake_backend
    app = MosaicTUIApp(backend=backend)

    async def run():
        async with app.run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause()
            # Unknown entity id → FakeBackend returns no provenance.
            screen = await _push_provenance(app, pilot, backend, "no-history")
            assert screen.has_class("empty")

    asyncio.run(run())


def test_provenance_escape_goes_back(seeded_fake_backend):
    from mosaic.tui.app import MosaicTUIApp

    backend = seeded_fake_backend
    sample_id = _sample_id(backend)
    app = MosaicTUIApp(backend=backend)

    async def run():
        async with app.run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause()
            await _push_provenance(app, pilot, backend, sample_id)
            assert isinstance(app.screen, ProvenanceScreen)
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, ProvenanceScreen)

    asyncio.run(run())
