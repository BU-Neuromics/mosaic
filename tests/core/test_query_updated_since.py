"""Tests for sec4 §4.5 ``query_updated_since`` polling support.

Verifies that ``MosaicClient.query_updated_since`` returns only entities
whose provenance-derived ``updated_at`` is strictly greater than the
``since`` watermark, ordered by ``updated_at`` ascending so polling
callers (e.g. Cappella's ``hippo_poll`` trigger) can advance their
watermark incrementally.
"""

from __future__ import annotations

import os
import tempfile
import time

import pytest

from mosaic.core.client import MosaicClient
from mosaic.core.exceptions import TemporalQueryError
from mosaic.core.storage.adapters.sqlite_adapter import SQLiteAdapter
from tests.conftest import _build_minimal_schema_registry


@pytest.fixture
def db_path() -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "test_updated_since.db")


@pytest.fixture
def client(db_path: str) -> MosaicClient:
    storage = SQLiteAdapter(db_path, schema_registry=_build_minimal_schema_registry())
    return MosaicClient(storage=storage, bypass_validation=True)


def _create(client: MosaicClient, name: str) -> str:
    """Create a Sample and return its id, with a small delay so
    provenance timestamps are strictly ordered."""
    result = client.put("Sample", {"name": name})
    time.sleep(0.005)
    return result["id"]


class TestQueryUpdatedSince:
    def test_returns_only_entities_updated_after_watermark(
        self, client: MosaicClient
    ) -> None:
        first_id = _create(client, "first")
        watermark = client.get("Sample", first_id)["updated_at"]

        second_id = _create(client, "second")
        third_id = _create(client, "third")

        result = client.query_updated_since("Sample", since=watermark)

        ids = [item["id"] for item in result.items]
        assert first_id not in ids
        assert ids == [second_id, third_id]
        assert result.total == 2

    def test_watermark_is_exclusive(self, client: MosaicClient) -> None:
        """An entity whose updated_at equals the watermark is excluded —
        callers persist the last-seen updated_at and must not see the
        same entity again on the next poll."""
        entity_id = _create(client, "only")
        watermark = client.get("Sample", entity_id)["updated_at"]

        result = client.query_updated_since("Sample", since=watermark)

        assert result.items == []
        assert result.total == 0

    def test_results_ordered_by_updated_at_ascending(
        self, client: MosaicClient
    ) -> None:
        ids = [_create(client, f"e{i}") for i in range(4)]

        result = client.query_updated_since(
            "Sample", since="2000-01-01T00:00:00Z"
        )

        updated_ats = [item["updated_at"] for item in result.items]
        assert updated_ats == sorted(updated_ats)
        assert [item["id"] for item in result.items] == ids

    def test_update_moves_entity_into_window(self, client: MosaicClient) -> None:
        """Replacing an old entity advances its updated_at past the
        watermark, so polling callers see modifications, not just
        creations."""
        old_id = _create(client, "old")
        watermark = client.get("Sample", old_id)["updated_at"]

        assert client.query_updated_since("Sample", since=watermark).items == []

        time.sleep(0.005)
        client.replace("Sample", old_id, {"name": "modified"})

        result = client.query_updated_since("Sample", since=watermark)
        assert [item["id"] for item in result.items] == [old_id]

    def test_limit_and_offset_paginate_within_window(
        self, client: MosaicClient
    ) -> None:
        ids = [_create(client, f"p{i}") for i in range(5)]

        page = client.query_updated_since(
            "Sample", since="2000-01-01T00:00:00Z", limit=2, offset=2
        )

        assert [item["id"] for item in page.items] == ids[2:4]
        assert page.total == 5
        assert page.limit == 2
        assert page.offset == 2

    def test_filters_compose_with_watermark(self, client: MosaicClient) -> None:
        client.put("Sample", {"name": "keep"})
        client.put("Sample", {"name": "drop"})

        result = client.query_updated_since(
            "Sample",
            since="2000-01-01T00:00:00Z",
            filters=[{"field": "name", "operator": "eq", "value": "keep"}],
        )

        assert [item["data"]["name"] for item in result.items] == ["keep"]

    def test_entity_type_none_polls_across_all_types(
        self, client: MosaicClient
    ) -> None:
        """``entity_type=None`` composes with the issue #44/#49 cross-class
        scan — the watermark filter runs over every type."""
        sample_id = _create(client, "s")

        result = client.query_updated_since(None, since="2000-01-01T00:00:00Z")

        assert sample_id in [item["id"] for item in result.items]

    def test_z_suffix_and_offset_timestamps_accepted(
        self, client: MosaicClient
    ) -> None:
        _create(client, "tz")

        for since in ("2000-01-01T00:00:00Z", "2000-01-01T00:00:00+00:00"):
            result = client.query_updated_since("Sample", since=since)
            assert result.total == 1

    def test_naive_watermark_treated_as_utc(self, client: MosaicClient) -> None:
        _create(client, "naive")

        result = client.query_updated_since("Sample", since="2000-01-01T00:00:00")
        assert result.total == 1

    def test_invalid_since_raises_temporal_query_error(
        self, client: MosaicClient
    ) -> None:
        with pytest.raises(TemporalQueryError) as exc_info:
            client.query_updated_since("Sample", since="not-a-timestamp")
        assert "not-a-timestamp" in exc_info.value.message

    def test_empty_since_raises_temporal_query_error(
        self, client: MosaicClient
    ) -> None:
        with pytest.raises(TemporalQueryError):
            client.query_updated_since("Sample", since="")
