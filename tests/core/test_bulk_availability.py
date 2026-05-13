"""Unit tests for HippoClient.set_availability_bulk() operation."""

import os
import tempfile

import pytest

from hippo.core.client import HippoClient
from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter
from tests.conftest import _build_minimal_schema_registry


class TestBulkAvailability:
    """Tests for HippoClient.set_availability_bulk()."""

    @pytest.fixture
    def db_path(self) -> str:
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "test_bulk_avail.db")

    @pytest.fixture
    def client(self, db_path: str) -> HippoClient:
        storage = SQLiteAdapter(db_path, schema_registry=_build_minimal_schema_registry())
        return HippoClient(storage=storage, bypass_validation=True)

    def test_bulk_set_unavailable(self, client: HippoClient) -> None:
        """Bulk-mark multiple entities as unavailable."""
        client.put("Sample", {"id": "b1", "name": "one"})
        client.put("Sample", {"id": "b2", "name": "two"})
        client.put("Sample", {"id": "b3", "name": "three"})

        result = client.set_availability_bulk(
            entity_type="Sample",
            entity_ids=["b1", "b2", "b3"],
            is_available=False,
        )

        assert result["total"] == 3
        assert result["succeeded"] == 3
        assert result["failed"] == 0

    def test_bulk_partial_failure(self, client: HippoClient) -> None:
        """Partial failure when some entities don't exist."""
        client.put("Sample", {"id": "b4", "name": "exists"})

        result = client.set_availability_bulk(
            entity_type="Sample",
            entity_ids=["b4", "nonexistent"],
            is_available=False,
        )

        assert result["total"] == 2
        assert result["succeeded"] == 1
        assert result["failed"] == 1
        assert result["failures"][0]["id"] == "nonexistent"

    def test_bulk_set_available(self, client: HippoClient) -> None:
        """Bulk-mark entities as available after making them unavailable."""
        client.put("Sample", {"id": "b5", "name": "test"})
        client.set_availability_bulk("Sample", ["b5"], is_available=False)

        result = client.set_availability_bulk("Sample", ["b5"], is_available=True)
        assert result["succeeded"] == 1

    def test_bulk_empty_list(self, client: HippoClient) -> None:
        """Empty entity list returns zero counts."""
        result = client.set_availability_bulk("Sample", [], is_available=False)

        assert result["total"] == 0
        assert result["succeeded"] == 0
        assert result["failed"] == 0

    def test_bulk_records_provenance(self, client: HippoClient) -> None:
        """Bulk availability change records provenance events."""
        client.put("Sample", {"id": "b6", "name": "test"})

        client.set_availability_bulk(
            entity_type="Sample",
            entity_ids=["b6"],
            is_available=False,
            reason="batch archival",
        )

        history = client.history("b6")
        # Legacy "AvailabilityChanged" → availability_change (Decision 9.6.B)
        availability_events = [
            h for h in history if h["operation_type"] == "availability_change"
        ]
        assert len(availability_events) >= 1
