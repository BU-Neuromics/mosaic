"""Unit tests for HippoClient.replace() (PUT semantics) operation."""

import os
import tempfile

import pytest

from hippo.core.client import HippoClient
from hippo.core.exceptions import EntityNotFoundError, ValidationFailure
from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter
from tests.conftest import _build_minimal_schema_registry


class TestReplaceOperation:
    """Tests for HippoClient.replace() operation."""

    @pytest.fixture
    def db_path(self) -> str:
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "test_replace.db")

    @pytest.fixture
    def client(self, db_path: str) -> HippoClient:
        storage = SQLiteAdapter(db_path, schema_registry=_build_minimal_schema_registry())
        return HippoClient(storage=storage, bypass_validation=True)

    def test_replace_overwrites_existing_entity(self, client: HippoClient) -> None:
        """Replace fully overwrites entity data."""
        client.put("Sample", {"id": "r1", "name": "original", "extra": "field"})

        result = client.replace("Sample", "r1", {"name": "replaced"})

        assert result["id"] == "r1"
        assert result["data"] == {"name": "replaced"}
        assert "extra" not in result["data"]
        assert result["version"] == 2

    def test_replace_returns_404_for_missing_entity(self, client: HippoClient) -> None:
        """Replace raises EntityNotFoundError for non-existent entity."""
        with pytest.raises(EntityNotFoundError):
            client.replace("Sample", "nonexistent", {"name": "test"})

    def test_replace_rejects_empty_data(self, client: HippoClient) -> None:
        """Replace rejects null/empty data."""
        client.put("Sample", {"id": "r2", "name": "test"})

        with pytest.raises(ValidationFailure):
            client.replace("Sample", "r2", {})

    def test_replace_records_provenance(self, client: HippoClient) -> None:
        """Replace records an 'update' provenance event (Decision 9.6.B)."""
        client.put("Sample", {"id": "r3", "name": "original"})
        client.replace("Sample", "r3", {"name": "replaced"})

        history = client.history("r3")
        op_types = [h["operation_type"] for h in history]
        # Legacy "REPLACED" → update per Decision 9.6.B.
        # put() emits one 'create' event; replace() adds one 'update'.
        assert op_types.count("update") >= 1

    def test_replace_increments_version(self, client: HippoClient) -> None:
        """Replace increments the entity version."""
        client.put("Sample", {"id": "r4", "name": "v1"})
        client.put("Sample", {"name": "v2"}, "r4")

        result = client.replace("Sample", "r4", {"name": "v3-replaced"})
        assert result["version"] == 3

    def test_replace_preserves_created_at(self, client: HippoClient) -> None:
        """Replace keeps the original created_at timestamp."""
        original = client.put("Sample", {"id": "r5", "name": "orig"})
        replaced = client.replace("Sample", "r5", {"name": "new"})

        assert replaced["created_at"] == original["created_at"]
        assert replaced["updated_at"] >= original["updated_at"]
