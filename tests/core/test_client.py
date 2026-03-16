"""Unit tests for HippoClient put, get, query operations."""

import json
import os
import sqlite3
import tempfile

import pytest

from hippo.core.client import HippoClient
from hippo.core.exceptions import EntityNotFoundError, ValidationFailure
from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter


class TestPutOperation:
    """Tests for HippoClient.put() operation."""

    @pytest.fixture
    def db_path(self) -> str:
        """Create a temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "test_put.db")

    @pytest.fixture
    def client(self, db_path: str) -> HippoClient:
        """Create a HippoClient with SQLite storage."""
        storage = SQLiteAdapter(db_path)
        return HippoClient(storage=storage, bypass_validation=True)

    def test_put_creates_entity_with_generated_id(self, client: HippoClient) -> None:
        """Test that put creates an entity with a generated UUID when no ID provided."""
        result = client.put("Sample", {"name": "test", "value": 123})

        assert "id" in result
        assert result["entity_type"] == "Sample"
        assert result["data"] == {"name": "test", "value": 123}
        assert result["version"] == 1

    def test_put_creates_entity_with_provided_id(self, client: HippoClient) -> None:
        """Test that put uses provided ID when specified."""
        result = client.put("Sample", {"id": "my-id", "name": "test"})

        assert result["id"] == "my-id"

    def test_put_uses_id_from_data(self, client: HippoClient) -> None:
        """Test that put uses ID from data dict when entity_id not provided."""
        result = client.put("Sample", {"id": "data-id", "name": "test"})

        assert result["id"] == "data-id"

    def test_put_increments_version_on_update(self, client: HippoClient) -> None:
        """Test that version is incremented when updating an existing entity."""
        result1 = client.put("Sample", {"id": "v-test", "name": "v1"})
        assert result1["version"] == 1

        result2 = client.put("Sample", {"name": "v2"}, "v-test")
        assert result2["version"] == 2

        result3 = client.put("Sample", {"name": "v3"}, "v-test")
        assert result3["version"] == 3

    def test_put_rejects_null_data(self, client: HippoClient) -> None:
        """Test that put rejects null data with ValidationFailure."""
        with pytest.raises(ValidationFailure) as exc_info:
            client.put("Sample", None)

        assert "null or empty" in str(exc_info.value).lower()

    def test_put_rejects_empty_data(self, client: HippoClient) -> None:
        """Test that put rejects empty data with ValidationFailure."""
        with pytest.raises(ValidationFailure) as exc_info:
            client.put("Sample", {})

        assert "null or empty" in str(exc_info.value).lower()


class TestGetOperation:
    """Tests for HippoClient.get() operation."""

    @pytest.fixture
    def db_path(self) -> str:
        """Create a temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "test_get.db")

    @pytest.fixture
    def client(self, db_path: str) -> HippoClient:
        """Create a HippoClient with SQLite storage."""
        storage = SQLiteAdapter(db_path)
        return HippoClient(storage=storage, bypass_validation=True)

    def test_get_returns_entity_with_metadata(self, client: HippoClient) -> None:
        """Test that get returns entity with all metadata fields."""
        created = client.put("Sample", {"id": "get-test", "name": "test"})
        result = client.get("Sample", "get-test")

        assert result["id"] == "get-test"
        assert result["entity_type"] == "Sample"
        assert result["data"]["name"] == "test"
        assert result["version"] == 1
        assert "created_at" in result
        assert "updated_at" in result

    def test_get_raises_error_for_nonexistent_entity(self, client: HippoClient) -> None:
        """Test that get raises EntityNotFoundError for non-existent entity."""
        with pytest.raises(EntityNotFoundError) as exc_info:
            client.get("Sample", "non-existent")

        assert "non-existent" in str(exc_info.value)

    def test_get_raises_error_for_wrong_entity_type(self, client: HippoClient) -> None:
        """Test that get raises error when entity exists but wrong type."""
        client.put("Sample", {"id": "type-test", "name": "test"})

        with pytest.raises(EntityNotFoundError):
            client.get("OtherType", "type-test")


class TestQueryOperation:
    """Tests for HippoClient.query() operation."""

    @pytest.fixture
    def db_path(self) -> str:
        """Create a temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "test_query.db")

    @pytest.fixture
    def client(self, db_path: str) -> HippoClient:
        """Create a HippoClient with SQLite storage."""
        storage = SQLiteAdapter(db_path)
        return HippoClient(storage=storage, bypass_validation=True)

    def test_query_returns_matching_entities(self, client: HippoClient) -> None:
        """Test that query returns entities matching the entity type."""
        client.put("Sample", {"id": "q1", "name": "first"})
        client.put("Sample", {"id": "q2", "name": "second"})
        client.put("Other", {"id": "q3", "name": "third"})

        results = client.query("Sample")

        assert len(results) == 2
        ids = {r["id"] for r in results}
        assert ids == {"q1", "q2"}

    def test_query_returns_empty_list_for_no_matches(self, client: HippoClient) -> None:
        """Test that query returns empty list when no entities match."""
        client.put("Sample", {"id": "q1", "name": "test"})

        results = client.query("NonExistent")

        assert results == []

    def test_query_sorts_by_created_at_ascending(self, client: HippoClient) -> None:
        """Test that query returns results sorted by created_at ascending."""
        client.put("Sample", {"id": "last", "name": "last"})
        client.put("Sample", {"id": "first", "name": "first"})
        client.put("Sample", {"id": "middle", "name": "middle"})

        results = client.query("Sample")

        assert len(results) == 3
        created_at = [r["created_at"] for r in results]
        assert created_at == sorted(created_at)

    def test_query_filters_by_date_from(self, client: HippoClient) -> None:
        """Test that query filters entities by date_from."""
        client.put("Sample", {"id": "old", "name": "old"})
        client.put("Sample", {"id": "new", "name": "new"})

        results = client.query("Sample", date_from="2030-01-01")

        assert len(results) == 0

    def test_query_filters_by_date_to(self, client: HippoClient) -> None:
        """Test that query filters entities by date_to."""
        client.put("Sample", {"id": "old", "name": "old"})
        client.put("Sample", {"id": "new", "name": "new"})

        results = client.query("Sample", date_to="2020-01-01")

        assert len(results) == 0

    def test_query_respects_limit(self, client: HippoClient) -> None:
        """Test that query respects the limit parameter."""
        for i in range(5):
            client.put("Sample", {"id": f"q{i}", "name": f"name{i}"})

        results = client.query("Sample", limit=3)

        assert len(results) == 3

    def test_query_respects_offset(self, client: HippoClient) -> None:
        """Test that query respects the offset parameter."""
        for i in range(5):
            client.put("Sample", {"id": f"q{i}", "name": f"name{i}"})

        results = client.query("Sample", offset=3)

        assert len(results) == 2


class TestErrorCases:
    """Tests for error handling in HippoClient."""

    @pytest.fixture
    def db_path(self) -> str:
        """Create a temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "test_errors.db")

    @pytest.fixture
    def client(self, db_path: str) -> HippoClient:
        """Create a HippoClient with SQLite storage."""
        storage = SQLiteAdapter(db_path)
        return HippoClient(storage=storage, bypass_validation=True)

    def test_get_nonexistent_entity_raises_error(self, client: HippoClient) -> None:
        """Test that getting a non-existent entity raises EntityNotFoundError."""
        with pytest.raises(EntityNotFoundError):
            client.get("Sample", "does-not-exist")

    def test_get_with_wrong_type_raises_error(self, client: HippoClient) -> None:
        """Test that getting an entity with wrong type raises EntityNotFoundError."""
        client.put("Sample", {"id": "test", "name": "test"})

        with pytest.raises(EntityNotFoundError):
            client.get("WrongType", "test")

    def test_put_null_data_raises_validation_error(self, client: HippoClient) -> None:
        """Test that putting null data raises ValidationFailure."""
        with pytest.raises(ValidationFailure):
            client.put("Sample", None)

    def test_put_empty_data_raises_validation_error(self, client: HippoClient) -> None:
        """Test that putting empty data raises ValidationFailure."""
        with pytest.raises(ValidationFailure):
            client.put("Sample", {})


class TestFTSIntegration:
    """Tests for FTS metadata derivation from schema."""

    def test_client_with_no_schemas_has_empty_fts_metadata(self) -> None:
        """Test that client with no schemas has empty _fts_table_metadata."""
        client = HippoClient()
        assert hasattr(client, "_fts_table_metadata")
        assert client._fts_table_metadata == {}

    def test_client_with_schema_containing_fts_field_has_fts_metadata(self) -> None:
        """Test that client with schema containing FTS field builds FTS metadata."""
        from hippo.config.models import SchemaConfig, FieldDefinition
        from hippo.core.storage.fts import FTSTableMetadata

        # Create a simple schema with an FTS field
        schema = SchemaConfig(
            name="Sample",
            version="1.0",
            fields=[
                FieldDefinition(name="name", type="string", required=True),
                FieldDefinition(name="notes", type="string", search="fts5"),
            ],
        )

        client = HippoClient(schemas={"Sample": schema})
        assert hasattr(client, "_fts_table_metadata")
        assert len(client._fts_table_metadata) == 1
        assert "Sample" in client._fts_table_metadata
        assert len(client._fts_table_metadata["Sample"]) == 1
        meta = client._fts_table_metadata["Sample"][0]
        assert isinstance(meta, FTSTableMetadata)
        # Check the table name pattern from FTS field metadata
        assert len(meta.fields) == 1
        assert meta.fields[0].field_name == "notes"
        assert meta.source_entity_type == "Sample"

    def test_client_with_schema_containing_no_fts_fields_has_empty_fts_metadata(
        self,
    ) -> None:
        """Test that client with schema containing no FTS fields has empty _fts_table_metadata."""
        from hippo.config.models import SchemaConfig, FieldDefinition

        # Create a simple schema with no FTS fields
        schema = SchemaConfig(
            name="Sample",
            version="1.0",
            fields=[
                FieldDefinition(name="name", type="string", required=True),
                FieldDefinition(name="description", type="string"),
            ],
        )

        client = HippoClient(schemas={"Sample": schema})
        assert hasattr(client, "_fts_table_metadata")
        # No entry should be created for entities without FTS fields (they're not in the dict)
        assert "Sample" not in client._fts_table_metadata

    def test_client_with_multiple_entity_types_each_have_fts_fields(self) -> None:
        """Test that client with multiple entity types each having FTS fields populates both entries."""
        from hippo.config.models import SchemaConfig, FieldDefinition
        from hippo.core.storage.fts import FTSTableMetadata

        # Create schemas for two entities with FTS fields
        sample_schema = SchemaConfig(
            name="Sample",
            version="1.0",
            fields=[
                FieldDefinition(name="name", type="string", required=True),
                FieldDefinition(name="notes", type="string", search="fts5"),
            ],
        )

        project_schema = SchemaConfig(
            name="Project",
            version="1.0",
            fields=[
                FieldDefinition(name="title", type="string", required=True),
                FieldDefinition(name="description", type="string", search="fts5"),
            ],
        )

        client = HippoClient(
            schemas={"Sample": sample_schema, "Project": project_schema}
        )
        assert hasattr(client, "_fts_table_metadata")
        assert len(client._fts_table_metadata) == 2
        assert "Sample" in client._fts_table_metadata
        assert "Project" in client._fts_table_metadata
        assert len(client._fts_table_metadata["Sample"]) == 1
        assert len(client._fts_table_metadata["Project"]) == 1

        sample_meta = client._fts_table_metadata["Sample"][0]
        project_meta = client._fts_table_metadata["Project"][0]
        assert isinstance(sample_meta, FTSTableMetadata)
        assert isinstance(project_meta, FTSTableMetadata)
        # Check field names in the FTSFieldMetadata
        assert sample_meta.fields[0].field_name == "notes"
        assert project_meta.fields[0].field_name == "description"
