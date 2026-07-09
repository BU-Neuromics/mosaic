"""Tests for AvailabilityScreen and the status → is_available mapping."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip(
    "textual", reason="textual not installed; run: pip install datahelix-mosaic[tui]"
)

from textual.widgets import Input, Select

from mosaic.tui.backend.protocol import STATUS_VALUES
from mosaic.tui.widgets.availability_dialog import (
    AvailabilityScreen,
    compose_reason,
    status_to_availability,
)


# ---------------------------------------------------------------------------
# Unit tests: mapping helpers
# ---------------------------------------------------------------------------


def test_all_status_values_covered():
    assert STATUS_VALUES == (
        "active",
        "archived",
        "superseded",
        "deleted",
        "distributed",
        "removed",
    )


def test_only_active_is_available():
    assert status_to_availability("active") is True
    for status in ("archived", "superseded", "deleted", "distributed", "removed"):
        assert status_to_availability(status) is False


def test_compose_reason_with_and_without_note():
    assert compose_reason("archived", "") == "archived"
    assert compose_reason("archived", "freezer failure") == "archived: freezer failure"


# ---------------------------------------------------------------------------
# Pilot tests: dialog behaviour
# ---------------------------------------------------------------------------


def _dialog_app(fake_backend):
    from mosaic.tui.app import MosaicTUIApp

    return MosaicTUIApp(backend=fake_backend)


def test_dialog_apply_returns_transition(fake_backend):
    app = _dialog_app(fake_backend)
    results: list = []

    async def run():
        async with app.run_test(headless=True, size=(100, 40)) as pilot:
            await pilot.pause()
            dialog = AvailabilityScreen(entity_label="sample-1")
            await app.push_screen(dialog, results.append)
            await pilot.pause()

            dialog.query_one("#status-select", Select).value = "archived"
            dialog.query_one("#reason-input", Input).value = "end of study"
            dialog._apply()
            await pilot.pause()

    asyncio.run(run())
    assert results == [(False, "archived: end of study")]


def test_dialog_active_status_maps_to_available(fake_backend):
    app = _dialog_app(fake_backend)
    results: list = []

    async def run():
        async with app.run_test(headless=True, size=(100, 40)) as pilot:
            await pilot.pause()
            dialog = AvailabilityScreen(entity_label="sample-1")
            await app.push_screen(dialog, results.append)
            await pilot.pause()
            dialog._apply()  # default status is "active"
            await pilot.pause()

    asyncio.run(run())
    assert results == [(True, "active")]


def test_dialog_escape_cancels(fake_backend):
    app = _dialog_app(fake_backend)
    results: list = []

    async def run():
        async with app.run_test(headless=True, size=(100, 40)) as pilot:
            await pilot.pause()
            dialog = AvailabilityScreen(entity_label="sample-1")
            await app.push_screen(dialog, results.append)
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()

    asyncio.run(run())
    assert results == [None]
