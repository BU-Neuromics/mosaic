"""Unit tests for OR filter composition in queries."""

import os
import tempfile

import pytest

from hippo.core.client import HippoClient
from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter
from tests.conftest import _build_minimal_schema_registry


class TestORFilterComposition:
    """Tests for filter_mode='or' in HippoClient.query()."""

    @pytest.fixture
    def db_path(self) -> str:
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "test_or_filter.db")

    @pytest.fixture
    def client(self, db_path: str) -> HippoClient:
        storage = SQLiteAdapter(db_path, schema_registry=_build_minimal_schema_registry())
        c = HippoClient(storage=storage, bypass_validation=True)
        # Seed test data
        c.put("Sample", {"id": "s1", "name": "Alpha", "tissue": "brain"})
        c.put("Sample", {"id": "s2", "name": "Beta", "tissue": "liver"})
        c.put("Sample", {"id": "s3", "name": "Gamma", "tissue": "heart"})
        return c

    def test_and_filter_default(self, client: HippoClient) -> None:
        """Default AND mode: both filters must match."""
        result = client.query(
            entity_type="Sample",
            filters=[{"name": "Alpha"}, {"tissue": "liver"}],
            filter_mode="and",
        )
        # Alpha has brain, not liver — AND yields no match
        assert result.total == 0

    def test_or_filter_matches_either(self, client: HippoClient) -> None:
        """OR mode: either filter can match."""
        result = client.query(
            entity_type="Sample",
            filters=[{"name": "Alpha"}, {"tissue": "liver"}],
            filter_mode="or",
        )
        ids = {item["id"] for item in result.items}
        assert "s1" in ids  # matches name=Alpha
        assert "s2" in ids  # matches tissue=liver

    def test_or_filter_no_match(self, client: HippoClient) -> None:
        """OR mode with no matching filters returns empty."""
        result = client.query(
            entity_type="Sample",
            filters=[{"name": "Nonexistent"}, {"tissue": "kidney"}],
            filter_mode="or",
        )
        assert result.total == 0

    def test_or_filter_single_filter(self, client: HippoClient) -> None:
        """OR mode with single filter behaves like AND."""
        result = client.query(
            entity_type="Sample",
            filters=[{"name": "Beta"}],
            filter_mode="or",
        )
        assert result.total == 1
        assert result.items[0]["id"] == "s2"

    def test_empty_filters_returns_all(self, client: HippoClient) -> None:
        """No filters returns all entities regardless of filter_mode."""
        result_and = client.query(entity_type="Sample", filter_mode="and")
        result_or = client.query(entity_type="Sample", filter_mode="or")
        assert result_and.total == result_or.total == 3
