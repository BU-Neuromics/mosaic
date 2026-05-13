"""Unit tests for provenance-derived temporal fields (Gap 1) and PaginatedResult (Gap 2)."""

import os
import tempfile
import time

import pytest

from hippo.core.client import HippoClient
from hippo.core.storage.adapters.sqlite_adapter import SQLiteAdapter
from tests.conftest import _build_minimal_schema_registry
from hippo.core.types import PaginatedResult


class TestProvenanceDerivedFields:
    """Tests for Gap 1: created_at and updated_at derived from provenance log."""

    @pytest.fixture
    def db_path(self) -> str:
        """Create a temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "test_prov_fields.db")

    @pytest.fixture
    def client(self, db_path: str) -> HippoClient:
        """Create a HippoClient with SQLite storage."""
        storage = SQLiteAdapter(db_path, schema_registry=_build_minimal_schema_registry())
        return HippoClient(storage=storage, bypass_validation=True)

    def test_get_returns_provenance_derived_created_at(
        self, client: HippoClient
    ) -> None:
        """get() returns created_at equal to the first provenance CREATE timestamp."""
        result = client.put("Sample", {"id": "prov-1", "name": "test"})
        entity = client.get("Sample", "prov-1")

        # Fetch the provenance-derived timestamp directly for comparison.
        storage = client._storage
        with storage._transaction() as conn:
            prov_store = storage._get_provenance_store(conn)
            prov_ts = prov_store.get_provenance_timestamps("prov-1")

        assert prov_ts is not None
        assert entity["created_at"] == prov_ts["created_at"]

    def test_get_updated_at_reflects_most_recent_write(
        self, client: HippoClient
    ) -> None:
        """After multiple updates, updated_at matches the most recent write event timestamp."""
        client.put("Sample", {"id": "prov-update", "name": "v1"})
        # Small sleep to ensure timestamps differ.
        time.sleep(0.01)
        client.put("Sample", {"name": "v2"}, "prov-update")
        time.sleep(0.01)
        client.put("Sample", {"name": "v3"}, "prov-update")

        entity = client.get("Sample", "prov-update")

        storage = client._storage
        with storage._transaction() as conn:
            prov_store = storage._get_provenance_store(conn)
            prov_ts = prov_store.get_provenance_timestamps("prov-update")

        assert prov_ts is not None
        assert entity["updated_at"] == prov_ts["updated_at"]

    def test_query_returns_provenance_derived_created_at(
        self, client: HippoClient
    ) -> None:
        """query() returns entities with created_at derived from provenance."""
        client.put("Sample", {"id": "batch-1", "name": "one"})
        client.put("Sample", {"id": "batch-2", "name": "two"})

        result = client.query("Sample")

        assert isinstance(result, PaginatedResult)
        assert len(result.items) == 2

        storage = client._storage
        for item in result.items:
            with storage._transaction() as conn:
                prov_store = storage._get_provenance_store(conn)
                prov_ts = prov_store.get_provenance_timestamps(item["id"])
            assert prov_ts is not None
            assert item["created_at"] == prov_ts["created_at"]

    def test_entity_table_has_no_stored_temporal_columns(self, client: HippoClient) -> None:
        """Phase E: entities table must not have created_at/updated_at columns (PTS-69)."""
        client.put("Sample", {"id": "cache-test", "name": "test"})

        storage = client._storage
        with storage._transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(entities)")
            col_names = {row[1] for row in cursor.fetchall()}

        assert "created_at" not in col_names
        assert "updated_at" not in col_names

    def test_temporal_fields_advance_via_provenance_on_update(self, client: HippoClient) -> None:
        """After an update, updated_at advances in the provenance view (not stored column)."""
        client.put("Sample", {"id": "cache-update", "name": "v1"})
        storage = client._storage

        with storage._transaction() as conn:
            prov_store = storage._get_provenance_store(conn)
            first_ts = prov_store.get_provenance_timestamps("cache-update")

        time.sleep(0.01)
        client.put("Sample", {"name": "v2"}, "cache-update")

        with storage._transaction() as conn:
            prov_store = storage._get_provenance_store(conn)
            second_ts = prov_store.get_provenance_timestamps("cache-update")

        assert first_ts is not None
        assert second_ts is not None
        assert second_ts["updated_at"] >= first_ts["updated_at"]


class TestPaginatedResult:
    """Tests for Gap 2: client.query() returns PaginatedResult."""

    @pytest.fixture
    def db_path(self) -> str:
        """Create a temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "test_paginated.db")

    @pytest.fixture
    def client(self, db_path: str) -> HippoClient:
        """Create a HippoClient with SQLite storage."""
        storage = SQLiteAdapter(db_path, schema_registry=_build_minimal_schema_registry())
        return HippoClient(storage=storage, bypass_validation=True)

    def test_non_empty_query_returns_paginated_result(
        self, client: HippoClient
    ) -> None:
        """Non-empty query returns a correct PaginatedResult."""
        client.put("Sample", {"id": "pg-1", "name": "one"})
        client.put("Sample", {"id": "pg-2", "name": "two"})
        client.put("Sample", {"id": "pg-3", "name": "three"})

        result = client.query("Sample")

        assert isinstance(result, PaginatedResult)
        assert len(result.items) == 3
        assert result.total == 3
        assert result.offset == 0

    def test_empty_query_returns_empty_paginated_result(
        self, client: HippoClient
    ) -> None:
        """Empty query returns PaginatedResult with items=[] and total=0."""
        result = client.query("NonExistentType")

        assert isinstance(result, PaginatedResult)
        assert result.items == []
        assert result.total == 0

    def test_total_reflects_count_ignoring_limit(self, client: HippoClient) -> None:
        """total reflects count of all matching entities, ignoring limit/offset."""
        for i in range(10):
            client.put("Sample", {"id": f"pg-limit-{i}", "name": f"item{i}"})

        result = client.query("Sample", limit=3)

        assert isinstance(result, PaginatedResult)
        assert len(result.items) == 3
        assert result.total == 10  # total ignores limit
        assert result.limit == 3

    def test_total_reflects_count_ignoring_offset(self, client: HippoClient) -> None:
        """total is unaffected by offset."""
        for i in range(5):
            client.put("Sample", {"id": f"pg-offset-{i}", "name": f"item{i}"})

        result = client.query("Sample", offset=3)

        assert isinstance(result, PaginatedResult)
        assert len(result.items) == 2
        assert result.total == 5  # total ignores offset
        assert result.offset == 3

    def test_paginated_result_items_are_iterable(self, client: HippoClient) -> None:
        """Callers can iterate result.items just like a bare list."""
        client.put("Sample", {"id": "iter-1", "name": "first"})
        client.put("Sample", {"id": "iter-2", "name": "second"})

        result = client.query("Sample")

        ids = [item["id"] for item in result.items]
        assert set(ids) == {"iter-1", "iter-2"}

    def test_query_returns_paginated_result_type(self, client: HippoClient) -> None:
        """client.query() return value is an instance of PaginatedResult."""
        client.put("Sample", {"id": "type-check", "name": "test"})

        result = client.query("Sample")

        assert isinstance(result, PaginatedResult)
        assert hasattr(result, "items")
        assert hasattr(result, "total")
        assert hasattr(result, "limit")
        assert hasattr(result, "offset")
