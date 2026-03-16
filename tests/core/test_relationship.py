"""Unit tests for RelationshipManager."""

import os
import tempfile

import pytest

from hippo.core.client import HippoClient
from hippo.core.exceptions import EntityNotFoundError, HippoError
from hippo.core.relationship import (
    RelationshipExistsError,
    RelationshipManager,
    RelationshipNotFoundError,
)
from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter


class TestRelateOperation:
    """Tests for RelationshipManager.relate() operation."""

    @pytest.fixture
    def db_path(self) -> str:
        """Create a temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "test_relate.db")

    @pytest.fixture
    def client(self, db_path: str) -> HippoClient:
        """Create a HippoClient with SQLite storage."""
        storage = SQLiteAdapter(db_path)
        return HippoClient(storage=storage, bypass_validation=True)

    @pytest.fixture
    def sample_entities(self, client: HippoClient) -> tuple[str, str]:
        """Create sample entities for testing."""
        donor = client.put("Donor", {"name": "John Doe"})
        sample = client.put("Sample", {"name": "Sample 001"})
        return donor["id"], sample["id"]

    def test_relate_creates_relationship(
        self, client: HippoClient, sample_entities: tuple[str, str]
    ) -> None:
        """Test that relate creates a relationship between entities."""
        donor_id, sample_id = sample_entities

        result = client.relationships.relate(
            source_id=donor_id,
            target_id=sample_id,
            relationship_type="donated",
        )

        assert result["source_id"] == donor_id
        assert result["target_id"] == sample_id
        assert result["relationship_type"] == "donated"

    def test_relate_stores_metadata(
        self, client: HippoClient, sample_entities: tuple[str, str]
    ) -> None:
        """Test that relate stores metadata with the relationship."""
        donor_id, sample_id = sample_entities

        result = client.relationships.relate(
            source_id=donor_id,
            target_id=sample_id,
            relationship_type="donated",
            metadata={"collection_date": "2024-01-15", "volume": 100},
        )

        assert result["metadata"] == {"collection_date": "2024-01-15", "volume": 100}

    def test_relate_rejects_empty_type(
        self, client: HippoClient, sample_entities: tuple[str, str]
    ) -> None:
        """Test that relate rejects empty relationship type."""
        donor_id, sample_id = sample_entities

        with pytest.raises(HippoError) as exc_info:
            client.relationships.relate(
                source_id=donor_id,
                target_id=sample_id,
                relationship_type="",
            )

        assert "empty" in str(exc_info.value).lower()

    def test_relate_rejects_self_reference(
        self, client: HippoClient, sample_entities: tuple[str, str]
    ) -> None:
        """Test that relate rejects self-referential relationships."""
        donor_id, _ = sample_entities

        with pytest.raises(HippoError) as exc_info:
            client.relationships.relate(
                source_id=donor_id,
                target_id=donor_id,
                relationship_type="self",
            )

        assert "self-referential" in str(exc_info.value).lower()

    def test_relate_validates_source_exists(
        self, client: HippoClient, sample_entities: tuple[str, str]
    ) -> None:
        """Test that relate validates source entity exists."""
        _, sample_id = sample_entities

        with pytest.raises(EntityNotFoundError) as exc_info:
            client.relationships.relate(
                source_id="nonexistent-id",
                target_id=sample_id,
                relationship_type="test",
            )

        assert "not found" in str(exc_info.value).lower()

    def test_relate_validates_target_exists(
        self, client: HippoClient, sample_entities: tuple[str, str]
    ) -> None:
        """Test that relate validates target entity exists."""
        donor_id, _ = sample_entities

        with pytest.raises(EntityNotFoundError) as exc_info:
            client.relationships.relate(
                source_id=donor_id,
                target_id="nonexistent-id",
                relationship_type="test",
            )

        assert "not found" in str(exc_info.value).lower()


class TestUnrelateOperation:
    """Tests for RelationshipManager.unrelate() operation."""

    @pytest.fixture
    def db_path(self) -> str:
        """Create a temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "test_unrelate.db")

    @pytest.fixture
    def client(self, db_path: str) -> HippoClient:
        """Create a HippoClient with SQLite storage."""
        storage = SQLiteAdapter(db_path)
        return HippoClient(storage=storage, bypass_validation=True)

    @pytest.fixture
    def sample_entities(self, client: HippoClient) -> tuple[str, str]:
        """Create sample entities for testing."""
        donor = client.put("Donor", {"name": "John Doe"})
        sample = client.put("Sample", {"name": "Sample 001"})
        return donor["id"], sample["id"]

    @pytest.fixture
    def related_entities(self, client: HippoClient) -> tuple[str, str]:
        """Create entities with a relationship."""
        donor = client.put("Donor", {"name": "John Doe"})
        sample = client.put("Sample", {"name": "Sample 001"})
        client.relationships.relate(
            source_id=donor["id"],
            target_id=sample["id"],
            relationship_type="donated",
        )
        return donor["id"], sample["id"]

    def test_unrelate_removes_relationship(
        self, client: HippoClient, related_entities: tuple[str, str]
    ) -> None:
        """Test that unrelate removes a relationship."""
        donor_id, sample_id = related_entities

        result = client.relationships.unrelate(
            source_id=donor_id,
            target_id=sample_id,
            relationship_type="donated",
        )

        assert result is True

    def test_unrelate_raises_when_not_found(
        self, client: HippoClient, sample_entities: tuple[str, str]
    ) -> None:
        """Test that unrelate raises error when relationship doesn't exist."""
        donor_id, sample_id = sample_entities

        with pytest.raises(RelationshipNotFoundError) as exc_info:
            client.relationships.unrelate(
                source_id=donor_id,
                target_id=sample_id,
                relationship_type="nonexistent",
            )

        assert "not found" in str(exc_info.value).lower()

    def test_unrelate_only_removes_specific_type(
        self, client: HippoClient, related_entities: tuple[str, str]
    ) -> None:
        """Test that unrelate only removes the specified relationship type."""
        donor_id, sample_id = related_entities

        client.relationships.relate(
            source_id=donor_id,
            target_id=sample_id,
            relationship_type="processed_from",
        )

        client.relationships.unrelate(
            source_id=donor_id,
            target_id=sample_id,
            relationship_type="donated",
        )

        remaining = client.relationships.find_relationships(
            source_id=donor_id, target_id=sample_id
        )
        assert len(remaining) == 1
        assert remaining[0]["relationship_type"] == "processed_from"


class TestTraverseOperation:
    """Tests for RelationshipManager.traverse() operation."""

    @pytest.fixture
    def db_path(self) -> str:
        """Create a temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "test_traverse.db")

    @pytest.fixture
    def client(self, db_path: str) -> HippoClient:
        """Create a HippoClient with SQLite storage."""
        storage = SQLiteAdapter(db_path)
        return HippoClient(storage=storage, bypass_validation=True)

    @pytest.fixture
    def hierarchy(self, client: HippoClient) -> dict[str, str]:
        """Create a hierarchy of entities for traversal testing."""
        project = client.put("Project", {"name": "Project Alpha"})
        study = client.put("Study", {"name": "Study 001"})
        donor = client.put("Donor", {"name": "John Doe"})
        sample = client.put("Sample", {"name": "Sample 001"})

        client.relationships.relate(project["id"], study["id"], "contains")
        client.relationships.relate(study["id"], donor["id"], "enrolls")
        client.relationships.relate(donor["id"], sample["id"], "donated")

        return {
            "project": project["id"],
            "study": study["id"],
            "donor": donor["id"],
            "sample": sample["id"],
        }

    def test_traverse_finds_connected_entities(
        self, client: HippoClient, hierarchy: dict[str, str]
    ) -> None:
        """Test that traverse finds all connected entities."""
        results = client.relationships.traverse(hierarchy["project"])

        assert len(results) >= 3

    def test_traverse_respects_max_depth(
        self, client: HippoClient, hierarchy: dict[str, str]
    ) -> None:
        """Test that traverse respects max_depth parameter."""
        results = client.relationships.traverse(hierarchy["project"], max_depth=2)

        depths = [r["depth"] for r in results]
        assert all(d <= 2 for d in depths)

    def test_traverse_filters_by_relationship_type(
        self, client: HippoClient, hierarchy: dict[str, str]
    ) -> None:
        """Test that traverse filters by relationship type."""
        results = client.relationships.traverse(
            hierarchy["project"], relationship_type="contains"
        )

        for r in results:
            if r["depth"] == 1:
                assert r["relationship_type"] == "contains"

    def test_traverse_raises_for_nonexistent_entity(self, client: HippoClient) -> None:
        """Test that traverse raises error for nonexistent entity."""
        with pytest.raises(EntityNotFoundError) as exc_info:
            client.relationships.traverse("nonexistent-id")

        assert "not found" in str(exc_info.value).lower()

    def test_traverse_caps_depth_at_100(
        self, client: HippoClient, hierarchy: dict[str, str]
    ) -> None:
        """Test that traverse caps depth at 100."""
        results = client.relationships.traverse(hierarchy["project"], max_depth=500)

        depths = [r["depth"] for r in results]
        assert all(d <= 100 for d in depths)


class TestFindRelationships:
    """Tests for RelationshipManager.find_relationships() operation."""

    @pytest.fixture
    def db_path(self) -> str:
        """Create a temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "test_find.db")

    @pytest.fixture
    def client(self, db_path: str) -> HippoClient:
        """Create a HippoClient with SQLite storage."""
        storage = SQLiteAdapter(db_path)
        return HippoClient(storage=storage, bypass_validation=True)

    @pytest.fixture
    def sample_entities(self, client: HippoClient) -> tuple[str, str]:
        """Create sample entities for testing."""
        donor = client.put("Donor", {"name": "John Doe"})
        sample = client.put("Sample", {"name": "Sample 001"})
        return donor["id"], sample["id"]

    def test_find_returns_empty_for_none(self, client: HippoClient) -> None:
        """Test that find returns empty list when no matches."""
        results = client.relationships.find_relationships()
        assert results == []
