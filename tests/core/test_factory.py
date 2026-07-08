"""Tests for the config-driven storage/client factory (issue #42).

The factory is the single construction path shared by the CLI, the TUI SDK
backend, and ``mosaic serve``: it resolves the storage backend through the
``hippo.storage_adapters`` entry-point group and assembles a configured
``MosaicClient`` (registry + storage adapter + validation pipeline).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mosaic.config import MosaicConfig
from mosaic.core.exceptions import AdapterError, ValidationFailure
from mosaic.core.factory import (
    DEFAULT_SQLITE_PATH,
    build_schema_registry,
    create_client,
    create_client_from_config,
    create_storage_adapter,
    load_config_autodetect,
    resolve_storage_adapter_class,
)
from mosaic.core.storage import EntityStore
from mosaic.core.storage.adapters.sqlite_adapter import SQLiteAdapter

_FIXTURE_SCHEMA = (
    Path(__file__).parents[1] / "fixtures" / "schemas" / "sample_schema.yaml"
)

_VALIDATORS_YAML = """\
validators:
  - name: volume_positive
    entity_types:
      - Sample
    on:
      - create
      - update
    condition: 'entity.volume_ml > 0'
    error: "volume_ml must be positive"
"""


# ---------------------------------------------------------------------------
# Entry-point resolution
# ---------------------------------------------------------------------------


def test_resolve_sqlite_backend():
    cls = resolve_storage_adapter_class("sqlite")
    assert cls is SQLiteAdapter
    assert issubclass(cls, EntityStore)


def test_resolve_postgres_backend_registered():
    # `postgres` is registered in the entry-point group. With the [postgres]
    # extra installed it loads to an EntityStore subclass; without it (e.g.
    # CI's plain .[dev] install) resolution fails with the install hint.
    try:
        import psycopg  # noqa: F401
    except ImportError:
        with pytest.raises(AdapterError) as exc:
            resolve_storage_adapter_class("postgres")
        assert "datahelix-mosaic[postgres]" in str(exc.value)
    else:
        cls = resolve_storage_adapter_class("postgres")
        assert issubclass(cls, EntityStore)


def test_resolve_unknown_backend_raises():
    with pytest.raises(AdapterError) as exc:
        resolve_storage_adapter_class("nope")
    msg = str(exc.value)
    assert "Unknown storage backend" in msg
    assert "sqlite" in msg  # error lists the registered backends


# ---------------------------------------------------------------------------
# create_storage_adapter
# ---------------------------------------------------------------------------


def test_create_storage_adapter_sqlite_explicit_path(tmp_path):
    registry = build_schema_registry(_FIXTURE_SCHEMA)
    adapter = create_storage_adapter(
        storage_backend="sqlite",
        database_url=str(tmp_path / "x.db"),
        registry=registry,
    )
    assert isinstance(adapter, SQLiteAdapter)
    assert Path(adapter.database_path) == tmp_path / "x.db"


def test_create_storage_adapter_sqlite_default_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    registry = build_schema_registry(_FIXTURE_SCHEMA)
    adapter = create_storage_adapter(storage_backend="sqlite", registry=registry)
    assert Path(adapter.database_path) == Path(DEFAULT_SQLITE_PATH)


def test_non_sqlite_backend_requires_database_url():
    registry = build_schema_registry(_FIXTURE_SCHEMA)
    with pytest.raises(AdapterError) as exc:
        create_storage_adapter(storage_backend="postgres", registry=registry)
    assert "requires a database_url" in str(exc.value)


# ---------------------------------------------------------------------------
# create_client — real persistence, validators, schema
# ---------------------------------------------------------------------------


def test_create_client_persists_and_reads_back(tmp_path):
    db = str(tmp_path / "db.sqlite")
    client = create_client(database_url=db, schema_path=_FIXTURE_SCHEMA)
    created = client.create("Project", {"name": "Alpha"})
    pid = created["id"]

    # A fresh client over the SAME database must see the persisted entity —
    # proves storage is real, not the storage=None echo stub.
    client2 = create_client(database_url=db, schema_path=_FIXTURE_SCHEMA)
    fetched = client2.get("Project", pid)
    assert fetched["data"]["name"] == "Alpha"


def test_create_client_wires_validators(tmp_path):
    validators = tmp_path / "validators.yaml"
    validators.write_text(_VALIDATORS_YAML)
    client = create_client(
        database_url=str(tmp_path / "db.sqlite"),
        schema_path=_FIXTURE_SCHEMA,
        validators_path=validators,
    )
    with pytest.raises(ValidationFailure):
        client.create("Sample", {"name": "bad", "volume_ml": -1.0})


def test_create_client_validation_disabled_skips_pipeline(tmp_path):
    validators = tmp_path / "validators.yaml"
    validators.write_text(_VALIDATORS_YAML)
    client = create_client(
        database_url=str(tmp_path / "db.sqlite"),
        schema_path=_FIXTURE_SCHEMA,
        validators_path=validators,
        validation_enabled=False,
    )
    # The CEL rule is not loaded, so the otherwise-valid write goes through.
    created = client.create("Sample", {"name": "ok", "volume_ml": -1.0})
    assert created["id"]


def test_create_client_from_config(tmp_path):
    cfg = MosaicConfig(
        schema_path=str(_FIXTURE_SCHEMA),
        database_url=str(tmp_path / "db.sqlite"),
        storage_backend="sqlite",
    )
    client = create_client_from_config(cfg)
    created = client.create("Project", {"name": "Beta"})
    assert created["id"]


# ---------------------------------------------------------------------------
# Config loading / auto-detection
# ---------------------------------------------------------------------------


def test_load_config_autodetect_explicit_path(tmp_path):
    cfg_path = tmp_path / "hippo.yaml"
    cfg_path.write_text(
        f"schema_path: {_FIXTURE_SCHEMA}\n"
        "storage_backend: sqlite\n"
        f"database_url: {tmp_path / 'x.db'}\n"
    )
    cfg = load_config_autodetect(cfg_path)
    assert cfg is not None
    assert cfg.storage_backend == "sqlite"


def test_load_config_autodetect_cwd_config_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.json").write_text(
        json.dumps(
            {"schema_path": "./schemas", "database_url": "./data/hippo.db"}
        )
    )
    cfg = load_config_autodetect()
    assert cfg is not None
    assert cfg.database_url == "./data/hippo.db"


def test_load_config_autodetect_none_when_absent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_config_autodetect() is None
