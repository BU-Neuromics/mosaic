"""Regression tests for issue #116: ingesting an id that already exists
under a different concrete class must raise a loud conflict rather than
silently dropping the row.

Repro shape: two concrete classes (``Sample``, ``Project``) sharing the
same ``id`` value. Before the fix, ``client.put()`` (used by both the
CLI ingest path and the SDK) resolved the id polymorphically via
``_entity_registry``, found the first-created entity under the *other*
class, and treated the second write as an update against the wrong
class's table — a silent no-op that reported success.
"""

from __future__ import annotations

import os
import tempfile
from typing import Iterator

import pytest

from mosaic.core.client import MosaicClient
from mosaic.core.exceptions import EntityTypeConflictError
from mosaic.core.storage.adapters.sqlite_adapter import SQLiteAdapter, SQLiteEntity
from mosaic.linkml_bridge import SchemaRegistry
from tests.support.linkml_schemas import build_registry


def _registry() -> SchemaRegistry:
    return build_registry(
        {
            "Sample": {
                "attributes": {
                    "id": {"identifier": True, "required": True},
                    "name": {"range": "string"},
                }
            },
            "Project": {
                "attributes": {
                    "id": {"identifier": True, "required": True},
                    "title": {"range": "string"},
                }
            },
        }
    )


@pytest.fixture
def db_path() -> Iterator[str]:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "conflict.db")


@pytest.fixture
def adapter(db_path: str) -> SQLiteAdapter:
    return SQLiteAdapter(db_path, schema_registry=_registry())


@pytest.fixture
def client(adapter: SQLiteAdapter) -> MosaicClient:
    return MosaicClient(
        storage=adapter,
        registry=adapter.schema_registry,
        bypass_validation=True,
    )


def test_put_same_id_different_class_raises_conflict(client: MosaicClient) -> None:
    client.put(entity_type="Sample", data={"id": "DUP-1", "name": "sample one"})

    with pytest.raises(EntityTypeConflictError) as excinfo:
        client.put(entity_type="Project", data={"id": "DUP-1", "title": "project one"})

    assert excinfo.value.entity_id == "DUP-1"
    assert excinfo.value.requested_entity_type == "Project"
    assert excinfo.value.existing_entity_type == "Sample"


def test_conflicting_put_does_not_silently_drop_data(client: MosaicClient) -> None:
    client.put(entity_type="Sample", data={"id": "DUP-2", "name": "sample two"})

    with pytest.raises(EntityTypeConflictError):
        client.put(entity_type="Project", data={"id": "DUP-2", "title": "project two"})

    # The original Sample row must be untouched, and no Project row exists.
    sample = client.get("Sample", "DUP-2")
    assert sample["data"]["name"] == "sample two"
    assert client.query("Project").items == []
    assert len(client.query("Sample").items) == 1


def test_replace_same_id_different_class_raises_conflict(client: MosaicClient) -> None:
    client.put(entity_type="Sample", data={"id": "DUP-3", "name": "sample three"})

    from mosaic.core.ingestion_service import IngestionService

    ingestion = IngestionService(
        storage=client._storage, schema_manager=client._schema_manager
    )
    with pytest.raises(EntityTypeConflictError):
        ingestion.replace(
            entity_type="Project",
            entity_id="DUP-3",
            data={"title": "project three"},
            bypass_validation=True,
        )


def test_storage_create_same_id_different_class_raises_conflict(
    adapter: SQLiteAdapter,
) -> None:
    adapter.create(
        SQLiteEntity(
            id="DUP-4", entity_type="Sample", is_available=True, version=1,
            data={"name": "sample four"},
        )
    )

    with pytest.raises(EntityTypeConflictError):
        adapter.create(
            SQLiteEntity(
                id="DUP-4", entity_type="Project", is_available=True, version=1,
                data={"title": "project four"},
            )
        )
