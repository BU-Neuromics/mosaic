"""Integration tests for MosaicClient external ID methods."""

import os
import tempfile

import pytest

from mosaic.core.client import MosaicClient
from mosaic.core.exceptions import EntityNotFoundError
from mosaic.core.storage.adapters.sqlite_adapter import SQLiteAdapter
from tests.conftest import _build_minimal_schema_registry


class TestMosaicClientExternalId:
    """Tests for MosaicClient external ID methods."""

    @pytest.fixture
    def db_path(self) -> str:
        """Create a temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "test_external_id_client.db")

    @pytest.fixture
    def client(self, db_path: str) -> MosaicClient:
        """Create a MosaicClient with SQLite storage."""
        storage = SQLiteAdapter(db_path, schema_registry=_build_minimal_schema_registry())
        return MosaicClient(storage=storage, bypass_validation=True)

    def test_register_external_id(self, client: MosaicClient) -> None:
        """Test registering an external ID for an entity."""
        entity = client.put("Sample", {"id": "test-1", "name": "test"})

        result = client.register_external_id(entity["id"], "EXT-001")

        assert result["entity_id"] == entity["id"]
        assert result["external_id"] == "EXT-001"
        assert result["superseded_at"] is None

    def test_register_external_id_invalid_entity(self, client: MosaicClient) -> None:
        """Test that registering external ID for non-existent entity raises error."""
        with pytest.raises(EntityNotFoundError):
            client.register_external_id("non-existent", "EXT-001")

    def test_get_by_external_id(self, client: MosaicClient) -> None:
        """Test getting an entity by external ID."""
        entity = client.put("Sample", {"id": "test-1", "name": "test"})
        client.register_external_id(entity["id"], "EXT-001")

        result = client.get_by_external_id("EXT-001")

        assert result["id"] == entity["id"]
        assert result["data"]["name"] == "test"
        assert result["external_id"] == "EXT-001"

    def test_get_by_external_id_not_found(self, client: MosaicClient) -> None:
        """Test that get_by_external_id raises error for non-existent ID."""
        with pytest.raises(EntityNotFoundError):
            client.get_by_external_id("NON-EXISTENT")

    def test_supersede_external_id(self, client: MosaicClient) -> None:
        """Test superseding an external ID."""
        entity = client.put("Sample", {"id": "test-1", "name": "test"})
        client.register_external_id(entity["id"], "EXT-001")

        result = client.supersede(entity["id"], "EXT-001", "EXT-002")

        assert result["external_id"] == "EXT-002"
        assert result["superseded_at"] is None

    def test_supersede_invalid_entity(self, client: MosaicClient) -> None:
        """Test that superseding for non-existent entity raises error."""
        with pytest.raises(EntityNotFoundError):
            client.supersede("non-existent", "OLD", "NEW")

    def test_list_external_ids(self, client: MosaicClient) -> None:
        """Test listing external IDs for an entity."""
        entity = client.put("Sample", {"id": "test-1", "name": "test"})
        client.register_external_id(entity["id"], "EXT-001")
        client.register_external_id(entity["id"], "EXT-002")

        results = client.list_external_ids(entity["id"])

        assert len(results) == 2
        external_ids = {r["external_id"] for r in results}
        assert external_ids == {"EXT-001", "EXT-002"}

    def test_list_external_ids_excludes_superseded(self, client: MosaicClient) -> None:
        """Test that list_external_ids excludes superseded by default."""
        entity = client.put("Sample", {"id": "test-1", "name": "test"})
        client.register_external_id(entity["id"], "EXT-001")
        client.supersede(entity["id"], "EXT-001", "EXT-002")

        results = client.list_external_ids(entity["id"])

        assert len(results) == 1
        assert results[0]["external_id"] == "EXT-002"

    def test_list_external_ids_include_superseded(self, client: MosaicClient) -> None:
        """Test that list_external_ids includes superseded when requested."""
        entity = client.put("Sample", {"id": "test-1", "name": "test"})
        client.register_external_id(entity["id"], "EXT-001")
        client.supersede(entity["id"], "EXT-001", "EXT-002")

        results = client.list_external_ids(entity["id"], include_superseded=True)

        assert len(results) == 2

    def test_get_by_external_id_returns_latest(self, client: MosaicClient) -> None:
        """Two entities may share an external-id value across distinct source
        systems; the most recently registered active mapping wins.

        Under the per-class ``ExternalID`` model, ``(source_system, value)``
        is unique within active records, so mapping the same value to two
        entities requires distinct source systems.
        """
        entity1 = client.put("Sample", {"id": "test-1", "name": "test1"})
        entity2 = client.put("Sample", {"id": "test-2", "name": "test2"})

        client.register_external_id(
            entity1["id"], "SHARED-EXT", source_system="STARLIMS"
        )
        client.register_external_id(
            entity2["id"], "SHARED-EXT", source_system="DONOR_DB"
        )

        result = client.get_by_external_id("SHARED-EXT")

        assert result["id"] == entity2["id"]

    def test_register_external_id_duplicate_in_source_system(
        self, client: MosaicClient
    ) -> None:
        """``(source_system, value)`` is unique among active mappings —
        registering the same pair twice raises an IntegrityError."""
        import sqlite3

        entity1 = client.put("Sample", {"id": "test-1", "name": "test1"})
        entity2 = client.put("Sample", {"id": "test-2", "name": "test2"})

        client.register_external_id(entity1["id"], "DUP-EXT")
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint"):
            client.register_external_id(entity2["id"], "DUP-EXT")

    def test_get_by_external_id_archived_entity(self, client: MosaicClient) -> None:
        """Test get_by_external_id with archived entities."""
        entity = client.put("Sample", {"id": "test-1", "name": "test"})
        client.register_external_id(entity["id"], "EXT-001")

        client.delete("Sample", entity["id"])

        result = client.get_by_external_id("EXT-001", include_archived=True)
        assert result["id"] == entity["id"]

        with pytest.raises(EntityNotFoundError):
            client.get_by_external_id("EXT-001", include_archived=False)
