"""Tests for the 'hippo tui' CLI command."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from hippo.cli.main import app


runner = CliRunner()


def _strip_ansi(s: str) -> str:
    """Remove ANSI escape sequences from a string."""
    return re.sub(r'\x1b\[[0-9;]*m', '', s)


# ---------------------------------------------------------------------------
# Help text accessible without Textual installed
# ---------------------------------------------------------------------------


def test_tui_help_available():
    """'hippo tui --help' should work without importing Textual."""
    result = runner.invoke(app, ["tui", "--help"])
    assert result.exit_code == 0
    assert "TUI" in result.output or "tui" in result.output.lower()


def test_tui_help_shows_backend_option():
    """Help text lists --backend option."""
    result = runner.invoke(app, ["tui", "--help"])
    assert "--backend" in _strip_ansi(result.output)


def test_tui_help_shows_url_option():
    """Help text lists --url option."""
    result = runner.invoke(app, ["tui", "--help"])
    assert "--url" in _strip_ansi(result.output)


def test_tui_help_shows_token_option():
    """Help text lists --token option."""
    result = runner.invoke(app, ["tui", "--help"])
    assert "--token" in _strip_ansi(result.output)


def test_tui_help_shows_db_option():
    """Help text lists --db option."""
    result = runner.invoke(app, ["tui", "--help"])
    assert "--db" in _strip_ansi(result.output)


# ---------------------------------------------------------------------------
# Missing Textual shows install error
# ---------------------------------------------------------------------------


def test_tui_missing_textual_shows_install_error():
    """Running 'hippo tui' without Textual shows the install guidance message."""
    import builtins

    original_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "hippo.tui.app":
            raise ImportError("No module named 'textual'")
        return original_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", mock_import):
        result = runner.invoke(app, ["tui"])

    # Should exit non-zero and the error output should mention the install guidance
    combined = result.output + str(result.exception or "")
    assert (
        result.exit_code != 0 or "TUI requires" in combined or "pip install" in combined
    )


# ---------------------------------------------------------------------------
# Flag-to-backend wiring
# ---------------------------------------------------------------------------


def _make_mock_app_module():
    """Return a mock module containing a mock HippoTUIApp class."""
    mock_app_cls = MagicMock()
    mock_app_instance = MagicMock()
    mock_app_cls.return_value = mock_app_instance
    mock_module = MagicMock()
    mock_module.HippoTUIApp = mock_app_cls
    return mock_module, mock_app_cls, mock_app_instance


def test_tui_sdk_mode_wires_db_flag():
    """--db flag is forwarded to SDKBackend as db_path."""
    created_kwargs: list[dict] = []

    def mock_create_backend(mode, **kwargs):
        created_kwargs.append({"mode": mode, **kwargs})
        return MagicMock()

    mock_module, mock_app_cls, _ = _make_mock_app_module()

    with (
        patch("hippo.tui.backend.create_backend", mock_create_backend),
        patch.dict(sys.modules, {"hippo.tui.app": mock_module}),
    ):
        result = runner.invoke(app, ["tui", "--db", "/tmp/test.db"])

    assert any(kw.get("db_path") == "/tmp/test.db" for kw in created_kwargs)


def test_tui_rest_mode_wires_url_and_token():
    """--backend rest --url --token flags are forwarded to RESTBackend."""
    created_kwargs: list[dict] = []

    def mock_create_backend(mode, **kwargs):
        created_kwargs.append({"mode": mode, **kwargs})
        return MagicMock()

    mock_module, mock_app_cls, _ = _make_mock_app_module()

    with (
        patch("hippo.tui.backend.create_backend", mock_create_backend),
        patch.dict(sys.modules, {"hippo.tui.app": mock_module}),
    ):
        result = runner.invoke(
            app,
            ["tui", "--backend", "rest", "--url", "http://host:9000", "--token", "tok"],
        )

    assert any(
        kw.get("mode") == "rest"
        and kw.get("url") == "http://host:9000"
        and kw.get("token") == "tok"
        for kw in created_kwargs
    )
