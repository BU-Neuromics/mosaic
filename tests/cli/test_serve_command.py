"""Regression tests for ``mosaic serve`` client wiring (issue #42).

Before the fix, ``serve`` called ``create_default_app()`` with no client, so
every request fell back to a no-arg ``MosaicClient()`` with ``storage=None`` —
a non-persistent echo stub. These tests pin that ``serve`` now builds a
configured client from config (or a default) and injects it into the app.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from mosaic.cli.main import app

runner = CliRunner()

_FIXTURE_SCHEMA = (
    Path(__file__).parents[1] / "fixtures" / "schemas" / "sample_schema.yaml"
)


def _capture_app(monkeypatch):
    """Patch uvicorn.run to capture the app instead of serving."""
    captured: dict = {}
    monkeypatch.setattr(
        "uvicorn.run",
        lambda application, **kwargs: captured.__setitem__("app", application),
    )
    return captured


def test_serve_injects_configured_client(tmp_path, monkeypatch):
    cfg = tmp_path / "hippo.yaml"
    cfg.write_text(
        f"schema_path: {_FIXTURE_SCHEMA}\n"
        "storage_backend: sqlite\n"
        f"database_url: {tmp_path / 'serve.db'}\n"
    )
    captured = _capture_app(monkeypatch)

    result = runner.invoke(app, ["serve", "--config", str(cfg)])

    assert result.exit_code == 0, result.output
    application = captured["app"]
    assert application.state.hippo_client is not None
    # Real, persistent storage — not the storage=None echo stub.
    assert application.state.hippo_client.storage is not None


def test_serve_default_fallback_without_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    captured = _capture_app(monkeypatch)

    result = runner.invoke(app, ["serve"])

    assert result.exit_code == 0, result.output
    assert "default SQLite" in result.output
    assert captured["app"].state.hippo_client.storage is not None


def test_serve_explicit_bad_config_fails_loudly(tmp_path, monkeypatch):
    bad = tmp_path / "broken.yaml"
    bad.write_text("schema_path:\n  - not\n  - a\n  - path\n")  # invalid shape
    _capture_app(monkeypatch)

    result = runner.invoke(app, ["serve", "--config", str(bad)])

    assert result.exit_code == 1
    assert "could not load config" in result.output.lower()
