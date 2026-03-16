"""Unit tests for search capability validation."""

import os
import tempfile

import pytest

from hippo.config.models import FieldDefinition, SchemaConfig
from hippo.core.client import HippoClient
from hippo.core.exceptions import SearchCapabilityError
from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter


class TestSearchCapabilities:
    """Tests for search_capabilities() method."""

    def test_sqlite_adapter_search_capabilities_returns_fts(self) -> None:
        """Test that SQLite adapter returns 'fts' as supported search mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            adapter = SQLiteAdapter(db_path)

            capabilities = adapter.search_capabilities()

            assert capabilities == {"fts"}
            adapter.close()

    def test_entity_store_abc_has_search_capabilities_method(self) -> None:
        """Test that EntityStore ABC defines search_capabilities method."""
        from hippo.core.storage import EntityStore

        assert hasattr(EntityStore, "search_capabilities")


class TestStartupValidation:
    """Tests for startup search capability validation."""

    def test_startup_succeeds_with_fts_search_mode(self) -> None:
        """Test that startup succeeds when schema declares search: fts with SQLite adapter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            storage = SQLiteAdapter(db_path)

            schema = SchemaConfig(
                name="TestSchema",
                version="1.0.0",
                fields=[
                    FieldDefinition(
                        name="name",
                        type="string",
                        search="fts",
                    ),
                ],
            )

            client = HippoClient(
                storage=storage, schemas={"TestEntity": schema}, bypass_validation=True
            )
            assert client is not None
            storage.close()

    def test_startup_raises_error_with_embedding_search_mode(self) -> None:
        """Test that SearchCapabilityError is raised when schema declares search: embedding with SQLite adapter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            storage = SQLiteAdapter(db_path)

            schema = SchemaConfig(
                name="TestSchema",
                version="1.0.0",
                fields=[
                    FieldDefinition(
                        name="description",
                        type="string",
                        search="embedding",
                    ),
                ],
            )

            with pytest.raises(SearchCapabilityError) as exc_info:
                HippoClient(
                    storage=storage,
                    schemas={"TestEntity": schema},
                    bypass_validation=True,
                )

            assert "embedding" in str(exc_info.value)
            storage.close()

    def test_startup_succeeds_when_adapter_inactive(self) -> None:
        """Test that startup succeeds when adapter is inactive regardless of schema search modes."""
        schema = SchemaConfig(
            name="TestSchema",
            version="1.0.0",
            fields=[
                FieldDefinition(
                    name="description",
                    type="string",
                    search="embedding",
                ),
            ],
        )

        client = HippoClient(
            storage=None, schemas={"TestEntity": schema}, bypass_validation=True
        )
        assert client is not None

    def test_startup_succeeds_without_schemas(self) -> None:
        """Test that startup succeeds when no schemas are provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            storage = SQLiteAdapter(db_path)

            client = HippoClient(storage=storage, schemas=None, bypass_validation=True)
            assert client is not None
            storage.close()


class TestFieldDefinitionValidateSearch:
    """Tests for FieldDefinition.validate_search()."""

    def test_validate_search_accepts_fts(self) -> None:
        """Test that validate_search accepts 'fts'."""
        field = FieldDefinition(name="test", type="string", search="fts")
        assert field.search == "fts"

    def test_validate_search_accepts_fts5(self) -> None:
        """Test that validate_search accepts 'fts5'."""
        field = FieldDefinition(name="test", type="string", search="fts5")
        assert field.search == "fts5"

    def test_validate_search_accepts_embedding(self) -> None:
        """Test that validate_search accepts 'embedding'."""
        field = FieldDefinition(name="test", type="string", search="embedding")
        assert field.search == "embedding"

    def test_validate_search_accepts_none(self) -> None:
        """Test that validate_search accepts None."""
        field = FieldDefinition(name="test", type="string", search=None)
        assert field.search is None

    def test_validate_search_rejects_invalid(self) -> None:
        """Test that validate_search rejects invalid values."""
        with pytest.raises(ValueError) as exc_info:
            FieldDefinition(name="test", type="string", search="invalid")

        assert "search must be either" in str(exc_info.value)
