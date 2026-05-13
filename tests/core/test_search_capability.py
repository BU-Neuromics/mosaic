"""Unit tests for search capability validation."""

import os
import tempfile

import pytest

from hippo.core.client import HippoClient
from hippo.core.exceptions import SearchCapabilityError
from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter
from tests.conftest import _build_minimal_schema_registry
from tests.support.linkml_schemas import build_registry


class TestSearchCapabilities:
    def test_sqlite_adapter_search_capabilities_returns_fts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            adapter = SQLiteAdapter(db_path, schema_registry=_build_minimal_schema_registry())
            assert adapter.search_capabilities() == {"fts"}
            adapter.close()

    def test_entity_store_abc_has_search_capabilities_method(self) -> None:
        from hippo.core.storage import EntityStore

        assert hasattr(EntityStore, "search_capabilities")


class TestStartupValidation:
    def test_startup_succeeds_with_fts_search_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            storage = SQLiteAdapter(db_path, schema_registry=_build_minimal_schema_registry())
            registry = build_registry(
                {
                    "TestEntity": {
                        "attributes": {
                            "id": {"identifier": True},
                            "name": {
                                "range": "string",
                                "annotations": {"hippo_search": "fts"},
                            },
                        }
                    }
                }
            )
            client = HippoClient(
                storage=storage, registry=registry, bypass_validation=True
            )
            assert client is not None
            storage.close()

    def test_startup_raises_error_with_embedding_search_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            storage = SQLiteAdapter(db_path, schema_registry=_build_minimal_schema_registry())
            registry = build_registry(
                {
                    "TestEntity": {
                        "attributes": {
                            "id": {"identifier": True},
                            "description": {
                                "range": "string",
                                "annotations": {"hippo_search": "embedding"},
                            },
                        }
                    }
                }
            )
            with pytest.raises(SearchCapabilityError) as exc_info:
                HippoClient(
                    storage=storage, registry=registry, bypass_validation=True
                )
            assert "embedding" in str(exc_info.value)
            storage.close()

    def test_startup_succeeds_when_adapter_inactive(self) -> None:
        registry = build_registry(
            {
                "TestEntity": {
                    "attributes": {
                        "id": {"identifier": True},
                        "description": {
                            "range": "string",
                            "annotations": {"hippo_search": "embedding"},
                        },
                    }
                }
            }
        )
        client = HippoClient(storage=None, registry=registry, bypass_validation=True)
        assert client is not None

    def test_startup_succeeds_without_schemas(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            storage = SQLiteAdapter(db_path, schema_registry=_build_minimal_schema_registry())
            client = HippoClient(storage=storage, registry=None, bypass_validation=True)
            assert client is not None
            storage.close()
