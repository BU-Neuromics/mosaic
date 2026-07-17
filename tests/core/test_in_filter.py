"""Unit tests for IN / set-membership filter composition (issue #102).

Mirrors ``tests/core/test_or_filter.py``'s structure and fixtures, adding
coverage for ``{"field": ..., "op": "in", "value": [...]}`` filters: the
predicate-pushdown prerequisite for issue #102. Also covers as-of parity
(mirrors ``tests/core/test_asof_reconstruction.py``) and the empty-list
edge case, which must match nothing rather than erroring or matching all.
"""

import os
import tempfile

import pytest

from mosaic.core.client import MosaicClient
from mosaic.core.storage import Query
from mosaic.core.storage.adapters.sqlite_adapter import SQLiteAdapter
from tests.conftest import _build_minimal_schema_registry

FUTURE = "2999-01-01T00:00:00+00:00"


class TestINFilterComposition:
    """Tests for ``op="in"`` filters in ``MosaicClient.query()``."""

    @pytest.fixture
    def db_path(self) -> str:
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "test_in_filter.db")

    @pytest.fixture
    def client(self, db_path: str) -> MosaicClient:
        storage = SQLiteAdapter(db_path, schema_registry=_build_minimal_schema_registry())
        c = MosaicClient(storage=storage, bypass_validation=True)
        c.put("Sample", {"id": "s1", "name": "Alpha", "tissue": "brain"})
        c.put("Sample", {"id": "s2", "name": "Beta", "tissue": "liver"})
        c.put("Sample", {"id": "s3", "name": "Gamma", "tissue": "heart"})
        return c

    def test_in_filter_matches_any_listed_value(self, client: MosaicClient) -> None:
        result = client.query(
            entity_type="Sample",
            filters=[{"field": "tissue", "op": "in", "value": ["brain", "heart"]}],
        )
        ids = {item["id"] for item in result.items}
        assert ids == {"s1", "s3"}

    def test_in_filter_single_value_list(self, client: MosaicClient) -> None:
        result = client.query(
            entity_type="Sample",
            filters=[{"field": "tissue", "op": "in", "value": ["liver"]}],
        )
        assert result.total == 1
        assert result.items[0]["id"] == "s2"

    def test_in_filter_no_match(self, client: MosaicClient) -> None:
        result = client.query(
            entity_type="Sample",
            filters=[{"field": "tissue", "op": "in", "value": ["kidney"]}],
        )
        assert result.total == 0

    def test_in_filter_empty_list_matches_nothing(self, client: MosaicClient) -> None:
        """An empty IN-list must short-circuit to "no rows match" — not
        raise (invalid ``IN ()`` SQL) and not silently match everything."""
        result = client.query(
            entity_type="Sample",
            filters=[{"field": "tissue", "op": "in", "value": []}],
        )
        assert result.total == 0

    def test_in_filter_composes_with_and(self, client: MosaicClient) -> None:
        """AND mode: IN filter plus an equality filter must both hold."""
        result = client.query(
            entity_type="Sample",
            filters=[
                {"field": "tissue", "op": "in", "value": ["brain", "liver"]},
                {"field": "name", "value": "Alpha"},
            ],
            filter_mode="and",
        )
        assert result.total == 1
        assert result.items[0]["id"] == "s1"

    def test_in_filter_composes_with_or(self, client: MosaicClient) -> None:
        """OR mode: either the IN filter or the equality filter may match."""
        result = client.query(
            entity_type="Sample",
            filters=[
                {"field": "tissue", "op": "in", "value": ["heart"]},
                {"field": "name", "value": "Beta"},
            ],
            filter_mode="or",
        )
        ids = {item["id"] for item in result.items}
        assert ids == {"s2", "s3"}

    def test_eq_op_explicit_matches_bare_shorthand(self, client: MosaicClient) -> None:
        """``op="eq"`` (explicit) behaves identically to the pre-#102 bare
        ``{field: value}`` shorthand — default-op backward compatibility."""
        explicit = client.query(
            entity_type="Sample",
            filters=[{"field": "name", "op": "eq", "value": "Alpha"}],
        )
        implicit = client.query(
            entity_type="Sample",
            filters=[{"field": "name", "value": "Alpha"}],
        )
        bare = client.query(entity_type="Sample", filters=[{"name": "Alpha"}])
        assert (
            {i["id"] for i in explicit.items}
            == {i["id"] for i in implicit.items}
            == {i["id"] for i in bare.items}
            == {"s1"}
        )

    def test_in_filter_as_of_query(self, client: MosaicClient, db_path: str) -> None:
        """As-of (Python-side) matcher supports ``op="in"`` too (SQLite
        as-of path mirrors the live column-predicate path)."""
        result = client.query(
            entity_type="Sample",
            filters=[{"field": "tissue", "op": "in", "value": ["brain", "heart"]}],
            as_of=FUTURE,
        )
        ids = {item["id"] for item in result.items}
        assert ids == {"s1", "s3"}

    def test_in_filter_as_of_empty_list_matches_nothing(
        self, client: MosaicClient
    ) -> None:
        result = client.query(
            entity_type="Sample",
            filters=[{"field": "tissue", "op": "in", "value": []}],
            as_of=FUTURE,
        )
        assert result.total == 0


class TestINFilterLowLevelAdapter:
    """Directly exercises ``SQLiteAdapter.find`` (bypassing ``MosaicClient``)
    to cover the ``_find_per_class`` typed-column IN predicate in isolation,
    mirroring ``test_postgres_adapter.py``'s ``test_find_with_or_filter``
    style for the SQLite side."""

    @pytest.fixture
    def adapter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            a = SQLiteAdapter(
                os.path.join(tmpdir, "test_in_filter_adapter.db"),
                schema_registry=_build_minimal_schema_registry(),
            )
            yield a
            a.close()

    def test_find_with_in_filter(self, adapter):
        from mosaic.core.storage.adapters.sqlite_adapter import SQLiteEntity

        adapter.create(
            SQLiteEntity(
                id="a1", entity_type="Sample", is_available=True, version=1,
                data={"name": "Alpha", "tissue": "blood"},
            )
        )
        adapter.create(
            SQLiteEntity(
                id="a2", entity_type="Sample", is_available=True, version=1,
                data={"name": "Beta", "tissue": "tissue"},
            )
        )
        adapter.create(
            SQLiteEntity(
                id="a3", entity_type="Sample", is_available=True, version=1,
                data={"name": "Gamma", "tissue": "bone"},
            )
        )

        query = Query(
            entity_type="Sample",
            filters=[{"field": "tissue", "op": "in", "value": ["blood", "tissue"]}],
        )
        results = list(adapter.find(query))
        assert {r.id for r in results} == {"a1", "a2"}

    def test_find_with_empty_in_filter_returns_nothing(self, adapter):
        from mosaic.core.storage.adapters.sqlite_adapter import SQLiteEntity

        adapter.create(
            SQLiteEntity(
                id="a1", entity_type="Sample", is_available=True, version=1,
                data={"name": "Alpha", "tissue": "blood"},
            )
        )

        query = Query(
            entity_type="Sample",
            filters=[{"field": "tissue", "op": "in", "value": []}],
        )
        results = list(adapter.find(query))
        assert results == []
