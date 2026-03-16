"""Integration tests for HippoClient external ID methods."""

import os
import tempfile

import pytest

from hippo.core.client import HippoClient
from hippo.core.exceptions import EntityNotFoundError
from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter


class TestHippoClientExternalId:
    """Tests for HippoClient external ID methods."""

    @pytest.fixture
    def db_path(self) -> str:
        """Create a temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "test_external_id_client.db")

    @pytest.fixture
    def client(self, db_path: str) -> HippoClient:
        """Create a HippoClient with SQLite storage."""
        storage = SQLiteAdapter(db_path)
        return HippoClient(storage=storage, bypass_validation=True)

    def test_register_external_id(self, client: HippoClient) -> None:
        """Test registering an external ID for an entity."""
        entity = client.put("Sample", {"id": "test-1", "name": "test"})

        result = client.register_external_id(entity["id"], "EXT-001")

        assert result["entity_id"] == entity["id"]
        assert result["external_id"] == "EXT-001"
        assert result["superseded_at"] is None

    def test_register_external_id_invalid_entity(self, client: HippoClient) -> None:
        """Test that registering external ID for non-existent entity raises error."""
        with pytest.raises(EntityNotFoundError):
            client.register_external_id("non-existent", "EXT-001")

    def test_get_by_external_id(self, client: HippoClient) -> None:
        """Test getting an entity by external ID."""
        entity = client.put("Sample", {"id": "test-1", "name": "test"})
        client.register_external_id(entity["id"], "EXT-001")

        result = client.get_by_external_id("EXT-001")

        assert result["id"] == entity["id"]
        assert result["data"]["name"] == "test"
        assert result["external_id"] == "EXT-001"

    def test_get_by_external_id_not_found(self, client: HippoClient) -> None:
        """Test that get_by_external_id raises error for non-existent ID."""
        with pytest.raises(EntityNotFoundError):
            client.get_by_external_id("NON-EXISTENT")

    def test_supersede_external_id(self, client: HippoClient) -> None:
        """Test superseding an external ID."""
        entity = client.put("Sample", {"id": "test-1", "name": "test"})
        client.register_external_id(entity["id"], "EXT-001")

        result = client.supersede(entity["id"], "EXT-001", "EXT-002")

        assert result["external_id"] == "EXT-002"
        assert result["superseded_at"] is None

    def test_supersede_invalid_entity(self, client: HippoClient) -> None:
        """Test that superseding for non-existent entity raises error."""
        with pytest.raises(EntityNotFoundError):
            client.supersede("non-existent", "OLD", "NEW")

    def test_list_external_ids(self, client: HippoClient) -> None:
        """Test listing external IDs for an entity."""
        entity = client.put("Sample", {"id": "test-1", "name": "test"})
        client.register_external_id(entity["id"], "EXT-001")
        client.register_external_id(entity["id"], "EXT-002")

        results = client.list_external_ids(entity["id"])

        assert len(results) == 2
        external_ids = {r["external_id"] for r in results}
        assert external_ids == {"EXT-001", "EXT-002"}

    def test_list_external_ids_excludes_superseded(self, client: HippoClient) -> None:
        """Test that list_external_ids excludes superseded by default."""
        entity = client.put("Sample", {"id": "test-1", "name": "test"})
        client.register_external_id(entity["id"], "EXT-001")
        client.supersede(entity["id"], "EXT-001", "EXT-002")

        results = client.list_external_ids(entity["id"])

        assert len(results) == 1
        assert results[0]["external_id"] == "EXT-002"

    def test_list_external_ids_include_superseded(self, client: HippoClient) -> None:
        """Test that list_external_ids includes superseded when requested."""
        entity = client.put("Sample", {"id": "test-1", "name": "test"})
        client.register_external_id(entity["id"], "EXT-001")
        client.supersede(entity["id"], "EXT-001", "EXT-002")

        results = client.list_external_ids(entity["id"], include_superseded=True)

        assert len(results) == 2

    def test_get_by_external_id_returns_latest(self, client: HippoClient) -> None:
        """Test that get_by_external_id returns the entity with latest created_at."""
        entity1 = client.put("Sample", {"id": "test-1", "name": "test1"})
        entity2 = client.put("Sample", {"id": "test-2", "name": "test2"})

        client.register_external_id(entity1["id"], "SHARED-EXT")
        client.register_external_id(entity2["id"], "SHARED-EXT")

        result = client.get_by_external_id("SHARED-EXT")

        assert result["id"] == entity2["id"]

    def test_get_by_external_id_archived_entity(self, client: HippoClient) -> None:
        """Test get_by_external_id with archived entities."""
        entity = client.put("Sample", {"id": "test-1", "name": "test"})
        client.register_external_id(entity["id"], "EXT-001")

        client.delete("Sample", entity["id"])

        result = client.get_by_external_id("EXT-001", include_archived=True)
        assert result["id"] == entity["id"]

        with pytest.raises(EntityNotFoundError):
            client.get_by_external_id("EXT-001", include_archived=False)
