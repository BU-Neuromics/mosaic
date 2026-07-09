"""Tests for QueryView — filter parsing, execution, FTS, capability gating."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip(
    "textual", reason="textual not installed; run: pip install datahelix-mosaic[tui]"
)

from textual.widgets import DataTable, Input, Label, Select

from mosaic.tui.views.query import QueryView, parse_filters


# ---------------------------------------------------------------------------
# Unit tests: filter parsing
# ---------------------------------------------------------------------------


def test_parse_filters_single():
    assert parse_filters("status=active") == [
        {"field": "status", "value": "active"}
    ]


def test_parse_filters_multiple_with_whitespace():
    assert parse_filters(" status = active ,  name=S1") == [
        {"field": "status", "value": "active"},
        {"field": "name", "value": "S1"},
    ]


def test_parse_filters_empty_and_trailing_commas():
    assert parse_filters("") == []
    assert parse_filters("status=active,") == [
        {"field": "status", "value": "active"}
    ]


def test_parse_filters_rejects_missing_equals():
    with pytest.raises(ValueError, match="field=value"):
        parse_filters("garbage")


def test_parse_filters_rejects_empty_field():
    with pytest.raises(ValueError, match="field=value"):
        parse_filters("=oops")


# ---------------------------------------------------------------------------
# Pilot tests
# ---------------------------------------------------------------------------


async def _open_query(app, pilot) -> QueryView:
    await app.open_query_view()
    await pilot.pause()
    return app.query_one(QueryView)


def test_query_filters_run_and_render(seeded_fake_backend):
    from mosaic.tui.app import MosaicTUIApp

    backend = seeded_fake_backend
    app = MosaicTUIApp(backend=backend)

    async def run():
        async with app.run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause()
            view = await _open_query(app, pilot)
            view.query_one("#entity-type-select", Select).value = "Sample"

            filters_input = view.query_one("#filters-input", Input)
            filters_input.focus()
            filters_input.value = "status=active"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()

            table = view.query_one("#results-table", DataTable)
            assert table.row_count == 1  # only S1 has status=active
            status = str(view.query_one("#query-status", Label).renderable)
            assert "1 Sample" in status

    asyncio.run(run())
    calls = [c for c in backend.calls if c[0] == "query_entities"]
    assert calls == [
        (
            "query_entities",
            ("Sample", [{"field": "status", "value": "active"}], "and", 1),
        )
    ]


def test_query_or_mode_is_passed_through(seeded_fake_backend):
    from mosaic.tui.app import MosaicTUIApp

    backend = seeded_fake_backend
    app = MosaicTUIApp(backend=backend)

    async def run():
        async with app.run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause()
            view = await _open_query(app, pilot)
            view.query_one("#entity-type-select", Select).value = "Sample"
            view.query_one("#filter-mode-select", Select).value = "or"

            filters_input = view.query_one("#filters-input", Input)
            filters_input.focus()
            filters_input.value = "name=S1, name=S2"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()

            table = view.query_one("#results-table", DataTable)
            assert table.row_count == 2

    asyncio.run(run())
    calls = [c for c in backend.calls if c[0] == "query_entities"]
    assert calls and calls[0][1][2] == "or"


def test_query_fts_runs_search(seeded_fake_backend):
    from mosaic.tui.app import MosaicTUIApp

    backend = seeded_fake_backend
    app = MosaicTUIApp(backend=backend)

    async def run():
        async with app.run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause()
            view = await _open_query(app, pilot)
            view.query_one("#entity-type-select", Select).value = "Sample"

            fts_input = view.query_one("#fts-input", Input)
            fts_input.focus()
            fts_input.value = "S2"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()

            table = view.query_one("#results-table", DataTable)
            assert table.row_count == 1

    asyncio.run(run())
    calls = [c for c in backend.calls if c[0] == "search_entities"]
    assert calls == [("search_entities", ("Sample", "S2", 50))]


def test_query_capability_gating_hides_filters(seeded_fake_backend):
    """Backends without filter support show a hint instead of the input."""
    from mosaic.tui.app import MosaicTUIApp

    backend = seeded_fake_backend
    backend.supports_filters = False
    app = MosaicTUIApp(backend=backend)

    async def run():
        async with app.run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause()
            view = await _open_query(app, pilot)
            assert not view.query("#filters-input")
            assert view.query("#filters-unsupported")
            assert view.query("#fts-input")

    asyncio.run(run())


def test_query_bad_filter_reports_error_without_calling_backend(
    seeded_fake_backend,
):
    from mosaic.tui.app import MosaicTUIApp
    from mosaic.tui.widgets.status_bar import StatusBar

    backend = seeded_fake_backend
    app = MosaicTUIApp(backend=backend)

    async def run():
        async with app.run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause()
            view = await _open_query(app, pilot)
            view.query_one("#entity-type-select", Select).value = "Sample"

            filters_input = view.query_one("#filters-input", Input)
            filters_input.focus()
            filters_input.value = "not-a-filter"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()

            status_bar = app.query_one(StatusBar)
            assert "field=value" in status_bar._error_message

    asyncio.run(run())
    assert not [c for c in backend.calls if c[0] == "query_entities"]


def test_query_result_row_opens_detail(seeded_fake_backend):
    from mosaic.tui.app import MosaicTUIApp
    from mosaic.tui.views.entity_detail import EntityDetailScreen

    backend = seeded_fake_backend
    app = MosaicTUIApp(backend=backend)

    async def run():
        async with app.run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause()
            view = await _open_query(app, pilot)
            view.query_one("#entity-type-select", Select).value = "Sample"

            filters_input = view.query_one("#filters-input", Input)
            filters_input.focus()
            filters_input.value = "name=S1"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()

            table = view.query_one("#results-table", DataTable)
            table.focus()
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()

            screen = app.screen
            assert isinstance(screen, EntityDetailScreen)
            assert screen._entity_type == "Sample"

    asyncio.run(run())
