"""Compatibility tests for the ``hippo`` → ``mosaic`` rename (ADR-0004).

Covers the WP-H6.1 checklist from ``design/sec9_handoff_mosaic_rename.md``:
import shim (warning + identity), CLI alias, entry-point dual registration,
config-file fallback, and env-var fallback.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
import warnings

import pytest


def _fresh_hippo(monkeypatch):
    """Force a fresh ``import hippo`` (drop cached shim modules)."""
    for name in [m for m in sys.modules if m == "hippo" or m.startswith("hippo.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)


class TestImportShim:
    def test_import_hippo_emits_deprecation_warning(self, monkeypatch):
        _fresh_hippo(monkeypatch)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            importlib.import_module("hippo")
        assert any(
            issubclass(w.category, DeprecationWarning)
            and "renamed to 'mosaic'" in str(w.message)
            for w in caught
        )

    def test_hippo_client_is_mosaic_client(self):
        import hippo
        import mosaic

        assert hippo.HippoClient is mosaic.MosaicClient
        assert mosaic.HippoClient is mosaic.MosaicClient

    def test_submodule_identity_through_finder(self):
        import mosaic.core.types

        from hippo.core.types import Filter  # noqa: F401 — legacy spelling

        import hippo.core.types

        assert hippo.core.types is mosaic.core.types

    def test_client_module_identity(self):
        import hippo.core.client
        import mosaic.core.client

        assert hippo.core.client is mosaic.core.client
        assert hippo.core.client.MosaicClient is mosaic.core.client.MosaicClient

    def test_isinstance_across_spellings(self, tmp_path):
        from hippo.core.client import HippoClient
        from mosaic.core.client import MosaicClient

        assert HippoClient is MosaicClient

    def test_version_matches(self):
        import hippo
        import mosaic

        assert hippo.__version__ == mosaic.__version__


class TestCliAlias:
    def _run(self, *argv: str):
        return subprocess.run(
            list(argv), capture_output=True, text=True, check=False
        )

    def test_hippo_help_exits_zero_with_stderr_notice(self):
        result = self._run("hippo", "--help")
        assert result.returncode == 0
        assert "renamed to 'mosaic'" in result.stderr
        assert "renamed to 'mosaic'" not in result.stdout

    def test_mosaic_help_is_clean(self):
        result = self._run("mosaic", "--help")
        assert result.returncode == 0
        assert "renamed" not in result.stderr


class _FakeEntryPoint:
    def __init__(self, name: str, value: str, obj):
        self.name = name
        self.value = value
        self._obj = obj

    def load(self):
        return self._obj


class _GroupedEntryPoints:
    def __init__(self, by_group):
        self._by_group = by_group

    def select(self, *, group: str):
        return list(self._by_group.get(group, []))


class TestEntryPointGroups:
    def _patch(self, monkeypatch, by_group):
        import importlib.metadata as md

        monkeypatch.setattr(
            md, "entry_points", lambda: _GroupedEntryPoints(by_group)
        )

    def test_legacy_group_plugin_is_discovered(self, monkeypatch):
        from mosaic.core.loaders import discovery
        from mosaic.testing.fake_reference_loader import FakeReferenceLoader

        ep = _FakeEntryPoint(
            "legacyfake",
            "mosaic.testing.fake_reference_loader:FakeReferenceLoader",
            FakeReferenceLoader,
        )
        self._patch(monkeypatch, {"hippo.reference_loaders": [ep]})

        names = [p["name"] for p in discovery.discover_reference_loaders()]
        assert names == ["legacyfake"]

    def test_dual_registered_plugin_loads_once(self, monkeypatch):
        from mosaic.core.loaders import discovery
        from mosaic.testing.fake_reference_loader import FakeReferenceLoader

        ep = _FakeEntryPoint(
            "dual",
            "mosaic.testing.fake_reference_loader:FakeReferenceLoader",
            FakeReferenceLoader,
        )
        self._patch(
            monkeypatch,
            {
                "mosaic.reference_loaders": [ep],
                "hippo.reference_loaders": [ep],
            },
        )

        names = [p["name"] for p in discovery.discover_reference_loaders()]
        assert names.count("dual") == 1

        pkg_names = [p["name"] for p in discovery.discover_schema_packages()]
        assert pkg_names.count("dual") == 1

    def test_legacy_storage_adapter_group_is_read(self, monkeypatch):
        from mosaic.core import factory
        from mosaic.core.storage.adapters.sqlite_adapter import SQLiteAdapter

        ep = _FakeEntryPoint(
            "legacysqlite",
            "mosaic.core.storage.adapters.sqlite_adapter:SQLiteAdapter",
            SQLiteAdapter,
        )
        import importlib.metadata as md

        monkeypatch.setattr(
            md,
            "entry_points",
            lambda **kw: _GroupedEntryPoints(
                {"hippo.storage_adapters": [ep]}
            ).select(group=kw["group"])
            if "group" in kw
            else _GroupedEntryPoints({"hippo.storage_adapters": [ep]}),
        )

        cls = factory.resolve_storage_adapter_class("legacysqlite")
        assert cls is SQLiteAdapter


class TestConfigFallback:
    def test_hippo_yaml_loads_with_warning(self, tmp_path, monkeypatch):
        (tmp_path / "hippo.yaml").write_text("schema_path: schema.yaml\n")
        monkeypatch.chdir(tmp_path)
        from mosaic.core.factory import load_config_autodetect

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            cfg = load_config_autodetect()
        assert cfg is not None
        assert any(
            issubclass(w.category, DeprecationWarning)
            and "hippo.yaml" in str(w.message)
            for w in caught
        )

    def test_mosaic_yaml_wins_silently(self, tmp_path, monkeypatch):
        (tmp_path / "mosaic.yaml").write_text("schema_path: new.yaml\n")
        (tmp_path / "hippo.yaml").write_text("schema_path: old.yaml\n")
        monkeypatch.chdir(tmp_path)
        from mosaic.core.factory import load_config_autodetect

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            cfg = load_config_autodetect()
        assert cfg is not None
        assert str(cfg.schema_path) == "new.yaml"
        assert not any(
            issubclass(w.category, DeprecationWarning) for w in caught
        )


class TestEnvFallback:
    def _reset_warned(self):
        from mosaic.config import env as env_mod

        env_mod._warned.clear()

    def test_legacy_hippo_cache_dir_honored_with_warning(
        self, tmp_path, monkeypatch
    ):
        self._reset_warned()
        monkeypatch.delenv("MOSAIC_CACHE_DIR", raising=False)
        monkeypatch.setenv("HIPPO_CACHE_DIR", str(tmp_path / "legacy"))
        from mosaic.core.client import MosaicClient

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            root = MosaicClient._reference_cache_root()
        assert root == tmp_path / "legacy"
        assert any(
            issubclass(w.category, DeprecationWarning)
            and "HIPPO_CACHE_DIR" in str(w.message)
            for w in caught
        )

    def test_mosaic_cache_dir_wins_when_both_set(self, tmp_path, monkeypatch):
        self._reset_warned()
        monkeypatch.setenv("MOSAIC_CACHE_DIR", str(tmp_path / "new"))
        monkeypatch.setenv("HIPPO_CACHE_DIR", str(tmp_path / "legacy"))
        from mosaic.core.client import MosaicClient

        assert MosaicClient._reference_cache_root() == tmp_path / "new"
