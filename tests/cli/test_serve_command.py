"""Regression tests for ``mosaic serve`` client wiring (issue #42).

Before the fix, ``serve`` called ``create_default_app()`` with no client, so
every request fell back to a no-arg ``MosaicClient()`` with ``storage=None`` —
a non-persistent echo stub. These tests pin that ``serve`` now builds a
configured client from config (or a default) and injects it into the app.
"""

from __future__ import annotations

import os
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


def _capture_run_kwargs(monkeypatch):
    """Patch uvicorn.run to capture its positional target + kwargs."""
    captured: dict = {}

    def _fake_run(target, **kwargs):
        captured["target"] = target
        captured["kwargs"] = kwargs

    monkeypatch.setattr("uvicorn.run", _fake_run)
    return captured


def test_serve_reload_passes_import_string_not_app_object(tmp_path, monkeypatch):
    """Regression test for issue #171.

    Before the fix, ``--reload``/``--workers`` were passed straight to
    ``uvicorn.run(app, reload=True, ...)`` with a live app *object* —
    uvicorn requires an import-string target for those modes (each
    reload/worker re-imports the app in its own subprocess) and exits 1
    otherwise. ``serve`` must instead hand uvicorn the
    ``mosaic.serve:create_app_from_env`` factory string with
    ``factory=True``.
    """
    cfg = tmp_path / "mosaic.yaml"
    cfg.write_text(
        f"schema_path: {_FIXTURE_SCHEMA}\n"
        "storage_backend: sqlite\n"
        f"database_url: {tmp_path / 'serve.db'}\n"
    )
    captured = _capture_run_kwargs(monkeypatch)

    try:
        result = runner.invoke(app, ["serve", "--config", str(cfg), "--reload"])

        assert result.exit_code == 0, result.output
        assert captured["target"] == "mosaic.serve:create_app_from_env"
        assert captured["kwargs"]["factory"] is True
        assert captured["kwargs"]["reload"] is True
        assert os.environ["MOSAIC_CONFIG"] == str(cfg)
    finally:
        # serve() sets these directly on os.environ (not via monkeypatch) so
        # the reload subprocess it spawns for real would inherit them; clean
        # up by hand so they don't leak into other tests.
        os.environ.pop("MOSAIC_CONFIG", None)
        os.environ.pop("MOSAIC_SERVE_GRAPHQL", None)
        os.environ.pop("MOSAIC_SERVE_GRAPHQL_MAX_DEPTH", None)


def test_serve_no_reload_or_workers_still_passes_app_object(tmp_path, monkeypatch):
    """The common case (no --reload/--workers) is unaffected by the fix."""
    captured = _capture_run_kwargs(monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()

    result = runner.invoke(app, ["serve"])

    assert result.exit_code == 0, result.output
    assert captured["target"].state.hippo_client is not None
    assert "factory" not in captured["kwargs"]


def test_create_app_from_env_rebuilds_configured_client(tmp_path, monkeypatch):
    """The factory that uvicorn re-imports must build the same deployment."""
    from mosaic.serve import create_app_from_env

    monkeypatch.delenv("MOSAIC_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()

    application = create_app_from_env()

    assert application.state.hippo_client is not None
    assert application.state.hippo_client.storage is not None
