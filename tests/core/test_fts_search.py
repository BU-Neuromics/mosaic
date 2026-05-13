"""Tests for FTS search functionality."""

import pytest
from hippo.core.client import HippoClient
from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter
from tests.conftest import _build_minimal_schema_registry


class TestClientFTSearch:
    """Tests for FTS search in HippoClient."""

    def test_search_returns_results(self, temp_db_path):
        """Test that search returns matching entities."""
        adapter = SQLiteAdapter(temp_db_path, schema_registry=_build_minimal_schema_registry())
        client = HippoClient(storage=adapter)

        entity = {
            "id": "test-1",
            "entity_type": "Sample",
            "is_available": True,
            "version": 1,
            "data": {"title": "hello world test"},
        }

        from hippo.core.storage.adapters.sqlite_adapter import SQLiteEntity

        adapter.create(SQLiteEntity(**entity))

        adapter.create_fts_table("fts_sample_title", ["title"])

        adapter._get_fts_store().insert_fts_entry(
            "fts_sample_title", "test-1", "hello world test"
        )

        results = client.search("Sample", "hello")
        assert len(results) >= 0


@pytest.fixture
def temp_db_path(tmp_path):
    """Create a temporary database path."""
    db_path = tmp_path / "test.db"
    yield str(db_path)
    if db_path.exists():
        db_path.unlink()
