"""Unit tests for ExternalIdStorageAdapter."""

import os
import tempfile

import pytest

from hippo.core.storage.adapters.sqlite_adapter import (
    ExternalIdStorageAdapter,
    SQLiteAdapter,
)


class TestExternalIdStorageAdapter:
    """Tests for ExternalIdStorageAdapter CRUD operations."""

    @pytest.fixture
    def db_path(self) -> str:
        """Create a temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "test_external_id.db")

    @pytest.fixture
    def adapter(self, db_path: str) -> SQLiteAdapter:
        """Create a SQLiteAdapter with external ID support."""
        return SQLiteAdapter(db_path)

    @pytest.fixture
    def external_id_store(self, adapter: SQLiteAdapter) -> ExternalIdStorageAdapter:
        """Create an ExternalIdStorageAdapter."""
        return adapter._get_external_id_store()

    @pytest.fixture
    def entity_id(self, adapter: SQLiteAdapter) -> str:
        """Create a test entity and return its ID."""
        result = adapter.create(
            type(
                "TestEntity",
                (),
                {
                    "id": "test-entity-1",
                    "entity_type": "Sample",
                    "is_available": True,
                    "version": 1,
                    "data": {"name": "test"},
                    "created_at": "2024-01-01T00:00:00",
                    "updated_at": "2024-01-01T00:00:00",
                },
            )()
        )
        return "test-entity-1"

    def test_create_external_id(self, adapter: SQLiteAdapter, entity_id: str) -> None:
        """Test creating an external ID for an entity."""
        external_id_store = adapter._get_external_id_store()

        record = external_id_store.create_external_id(entity_id, "EXT-001")

        assert record.id is not None
        assert record.entity_id == entity_id
        assert record.external_id == "EXT-001"
        assert record.created_at is not None
        assert record.superseded_at is None

    def test_get_entity_by_external_id(
        self, adapter: SQLiteAdapter, entity_id: str
    ) -> None:
        """Test retrieving an entity by external ID."""
        external_id_store = adapter._get_external_id_store()
        external_id_store.create_external_id(entity_id, "EXT-001")

        result = external_id_store.get_entity_by_external_id("EXT-001")

        assert result is not None
        assert result.entity_id == entity_id
        assert result.external_id == "EXT-001"

    def test_get_entity_by_external_id_not_found(self, adapter: SQLiteAdapter) -> None:
        """Test that get_entity_by_external_id returns None for non-existent ID."""
        external_id_store = adapter._get_external_id_store()

        result = external_id_store.get_entity_by_external_id("NON-EXISTENT")

        assert result is None

    def test_list_external_ids_for_entity(
        self, adapter: SQLiteAdapter, entity_id: str
    ) -> None:
        """Test listing all external IDs for an entity."""
        external_id_store = adapter._get_external_id_store()
        external_id_store.create_external_id(entity_id, "EXT-001")
        external_id_store.create_external_id(entity_id, "EXT-002")

        results = list(external_id_store.list_external_ids_for_entity(entity_id))

        assert len(results) == 2
        external_ids = {r.external_id for r in results}
        assert external_ids == {"EXT-001", "EXT-002"}

    def test_list_external_ids_excludes_superseded(
        self, adapter: SQLiteAdapter, entity_id: str
    ) -> None:
        """Test that list_external_ids_for_entity excludes superseded by default."""
        external_id_store = adapter._get_external_id_store()
        external_id_store.create_external_id(entity_id, "EXT-001")
        external_id_store.supersede_external_id(entity_id, "EXT-001", "EXT-002")

        results = list(external_id_store.list_external_ids_for_entity(entity_id))

        assert len(results) == 1
        assert results[0].external_id == "EXT-002"

    def test_list_external_ids_include_superseded(
        self, adapter: SQLiteAdapter, entity_id: str
    ) -> None:
        """Test that list_external_ids_for_entity includes superseded when requested."""
        external_id_store = adapter._get_external_id_store()
        external_id_store.create_external_id(entity_id, "EXT-001")
        external_id_store.supersede_external_id(entity_id, "EXT-001", "EXT-002")

        results = list(
            external_id_store.list_external_ids_for_entity(
                entity_id, include_superseded=True
            )
        )

        assert len(results) == 2
        external_ids = {r.external_id for r in results}
        assert external_ids == {"EXT-001", "EXT-002"}

    def test_supersede_external_id(
        self, adapter: SQLiteAdapter, entity_id: str
    ) -> None:
        """Test superseding an external ID."""
        external_id_store = adapter._get_external_id_store()
        original = external_id_store.create_external_id(entity_id, "EXT-001")

        new_record = external_id_store.supersede_external_id(
            entity_id, "EXT-001", "EXT-002"
        )

        assert new_record.external_id == "EXT-002"
        assert new_record.superseded_at is None

        superseded = external_id_store.get_entity_by_external_id("EXT-001")
        assert superseded is None or superseded.entity_id != entity_id

    def test_get_entity_by_external_id_returns_latest(
        self, adapter: SQLiteAdapter
    ) -> None:
        """Test that get_entity_by_external_id returns the latest by created_at."""
        entity1 = "test-entity-1"
        entity2 = "test-entity-2"

        adapter.create(
            type(
                "TestEntity",
                (),
                {
                    "id": entity1,
                    "entity_type": "Sample",
                    "is_available": True,
                    "version": 1,
                    "data": {"name": "test1"},
                    "created_at": "2024-01-01T00:00:00",
                    "updated_at": "2024-01-01T00:00:00",
                },
            )()
        )
        adapter.create(
            type(
                "TestEntity",
                (),
                {
                    "id": entity2,
                    "entity_type": "Sample",
                    "is_available": True,
                    "version": 1,
                    "data": {"name": "test2"},
                    "created_at": "2024-01-02T00:00:00",
                    "updated_at": "2024-01-02T00:00:00",
                },
            )()
        )

        external_id_store = adapter._get_external_id_store()
        external_id_store.create_external_id(entity1, "SHARED-EXT")
        external_id_store.create_external_id(entity2, "SHARED-EXT")

        result = external_id_store.get_entity_by_external_id("SHARED-EXT")

        assert result is not None
        assert result.entity_id == entity2
