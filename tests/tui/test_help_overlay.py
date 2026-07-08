"""Tests for HelpOverlay widget."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip(
    "textual", reason="textual not installed; run: pip install datahelix-mosaic[tui]"
)

from mosaic.tui.widgets.help_overlay import HelpOverlay, _SHORTCUTS


def test_shortcuts_not_empty():
    """The shortcuts list has entries."""
    assert len(_SHORTCUTS) > 0


def test_shortcuts_include_quit():
    """Quit shortcut is present."""
    keys = [key for key, _ in _SHORTCUTS]
    assert any("q" in k.lower() for k in keys)


def test_shortcuts_include_help():
    """Help shortcut is present."""
    assert any("?" in k for k, _ in _SHORTCUTS)


def test_shortcuts_include_esc():
    """Esc shortcut is present."""
    assert any("Esc" in k for k, _ in _SHORTCUTS)


def test_help_overlay_instantiation():
    """HelpOverlay can be instantiated."""
    overlay = HelpOverlay()
    assert overlay is not None


def test_help_overlay_dismiss_action():
    """HelpOverlay action_dismiss calls dismiss."""
    dismissed: list[bool] = []
    overlay = HelpOverlay()

    original_dismiss = overlay.dismiss

    def mock_dismiss(result=None):
        dismissed.append(True)

    overlay.dismiss = mock_dismiss
    overlay.action_dismiss()
    assert dismissed == [True]


def test_help_overlay_pilot_opens_on_question_mark():
    """? opens the help overlay; Esc dismisses it."""
    from mosaic.tui.app import MosaicTUIApp
    from mosaic.tui.backend.protocol import EntityTypeSummary, PagedResult, SchemaView

    class MockBackend:
        async def list_entity_types(self):
            return [EntityTypeSummary("Sample", 0)]

        async def list_entities(self, *a, **kw):
            return PagedResult(items=[], page=1, total_pages=1, total_items=0)

        async def get_entity(self, *a, **kw):
            from mosaic.tui.backend.protocol import EntityDetail

            return EntityDetail(
                id="x", entity_type="Sample", fields={}, relationships=[]
            )

        async def get_schema(self):
            return SchemaView()

        async def get_provenance(self, *a, **kw):
            return []

    app = MosaicTUIApp(backend=MockBackend())

    async def run():
        async with app.run_test(headless=True, size=(80, 24)) as pilot:
            await pilot.pause()
            # Open help overlay
            await pilot.press("question_mark")
            await pilot.pause()
            # Should now have HelpOverlay in screen stack
            screen_count_after_open = len(app.screen_stack)
            assert screen_count_after_open > 1
            # Dismiss
            await pilot.press("escape")
            await pilot.pause()
            assert len(app.screen_stack) < screen_count_after_open
            await pilot.press("q")

    asyncio.run(run())
