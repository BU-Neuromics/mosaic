"""Tests for StatusBar widget."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip(
    "textual", reason="textual not installed; run: pip install datahelix-mosaic[tui]"
)

from mosaic.tui.widgets.status_bar import StatusBar


def test_status_bar_set_backend_sdk():
    """set_backend stores mode and target (no UI needed for logic)."""
    bar = StatusBar()
    bar._backend_mode = ""
    bar._connection_target = ""
    bar.set_backend("sdk", "hippo.db")
    text = bar._build_text()
    assert "sdk" in text
    assert "hippo.db" in text


def test_status_bar_set_backend_rest():
    """REST mode shows URL."""
    bar = StatusBar()
    bar.set_backend("rest", "http://host:8000")
    text = bar._build_text()
    assert "rest" in text
    assert "http://host:8000" in text


def test_status_bar_error_mode():
    """Error message is shown when set_error is called."""
    bar = StatusBar()
    bar.set_error("Connection refused")
    text = bar._build_text()
    assert "Connection refused" in text
    assert "ERROR" in text


def test_status_bar_clear_error():
    """Clearing error restores normal display."""
    bar = StatusBar()
    bar.set_backend("sdk", "hippo.db")
    bar.set_error("oops")
    bar.clear_error()
    text = bar._build_text()
    assert "ERROR" not in text
    assert "sdk" in text


def test_status_bar_entity_count_in_text():
    """Entity count is included in the text when > 0."""
    bar = StatusBar()
    bar.set_backend("sdk", "hippo.db")
    bar.entity_count = 42
    text = bar._build_text()
    assert "42" in text


def test_status_bar_sdk_path_display():
    """Status bar displays 'sdk | <path>' format."""
    bar = StatusBar()
    bar.set_backend("sdk", "hippo.db")
    text = bar._build_text()
    assert "sdk" in text and "hippo.db" in text


def test_status_bar_rest_url_display():
    """Status bar displays 'rest | <url>' format."""
    bar = StatusBar()
    bar.set_backend("rest", "http://host:8000")
    text = bar._build_text()
    assert "rest" in text and "http://host:8000" in text
