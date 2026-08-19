"""Aggregation & ordering surface (ADR-0007, issue #156).

Covers the SDK layer: ``order_by``/``order_dir`` pushdown on ``query()``
(SQL ORDER BY + LIMIT/OFFSET, NULLs last, stable ``id`` tiebreak, total via
COUNT(*)), the ``count``/``facet_counts``/``field_range`` client methods,
and the pinned rules — availability consistency (aggregates see exactly
what list queries see) and the as-of gate decisions. Postgres parity for
the same surface lives in ``tests/integration/test_postgres_adapter.py``.
"""

import os
import tempfile

import pytest

from mosaic.core.client import MosaicClient
from mosaic.core.exceptions import ValidationError
from mosaic.core.storage import Query
from mosaic.core.storage.adapters.sqlite_adapter import SQLiteAdapter
from mosaic.linkml_bridge import SchemaRegistry

from tests.core.test_comparison_filters import SCHEMA

FUTURE = "2999-01-01T00:00:00+00:00"


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry.from_yaml(SCHEMA)


@pytest.fixture
def client(registry: SchemaRegistry):
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_aggregation.db")
        storage = SQLiteAdapter(db_path, schema_registry=registry)
        c = MosaicClient(storage=storage, bypass_validation=True)
        c.put(
            "Specimen",
            {
                "id": "s1",
                "name": "Alpha",
                "age": 45,
                "score": 1.5,
                "collected_on": "2024-01-10",
                "is_tumor": False,
            },
        )
        c.put(
            "Specimen",
            {
                "id": "s2",
                "name": "Beta",
                "age": 60,
                "score": 2.5,
                "collected_on": "2025-03-05",
                "is_tumor": True,
            },
        )
        c.put(
            "Specimen",
            {
                "id": "s3",
                "name": "Gamma",
                "age": 75,
                "score": 3.5,
                "collected_on": "2026-06-20",
                "is_tumor": False,
            },
        )
        c.put(
            "Specimen",
            {
                "id": "s4",
                "name": "Delta",
                # no age / score / collected_on — the NULLs-last target
                "is_tumor": True,
            },
        )
        yield c


def ordered_ids(client, **kwargs) -> list[str]:
    return [i["id"] for i in client.query("Specimen", **kwargs).items]


class TestOrderByPushdown:
    def test_order_asc_nulls_last(self, client):
        assert ordered_ids(client, order_by="age") == ["s1", "s2", "s3", "s4"]

    def test_order_desc_nulls_still_last(self, client):
        assert ordered_ids(client, order_by="age", order_dir="desc") == [
            "s3",
            "s2",
            "s1",
            "s4",
        ]

    def test_order_by_string_column(self, client):
        assert ordered_ids(client, order_by="name") == ["s1", "s2", "s4", "s3"]

    def test_order_by_date_column(self, client):
        assert ordered_ids(client, order_by="collected_on", order_dir="desc") == [
            "s3",
            "s2",
            "s1",
            "s4",
        ]

    def test_id_tiebreak_is_stable(self, client):
        # is_tumor has two rows per value: ties break by id ascending.
        assert ordered_ids(client, order_by="is_tumor") == ["s1", "s3", "s2", "s4"]

    def test_pagination_pushdown_with_total(self, client):
        page = client.query("Specimen", order_by="age", limit=2, offset=1)
        assert [i["id"] for i in page.items] == ["s2", "s3"]
        assert page.total == 4  # whole match set, not the page

    def test_limit_zero_returns_no_rows_with_total(self, client):
        page = client.query("Specimen", order_by="age", limit=0)
        assert page.items == []
        assert page.total == 4  # issue #130 discipline preserved

    def test_order_composes_with_filters(self, client):
        page = client.query(
            "Specimen",
            filters=[{"field": "age", "op": "gte", "value": 60}],
            order_by="age",
            order_dir="desc",
        )
        assert [i["id"] for i in page.items] == ["s3", "s2"]
        assert page.total == 2

    def test_ordered_page_carries_temporal_fields(self, client):
        page = client.query("Specimen", order_by="age", limit=1)
        assert page.items[0]["created_at"] is not None

    def test_default_path_unchanged_without_order_by(self, client):
        # No order_by → the historical created_at-ascending Python order.
        assert ordered_ids(client) == ["s1", "s2", "s3", "s4"]

    def test_unknown_order_column_raises(self, client):
        with pytest.raises(ValidationError, match="order_by"):
            client.query("Specimen", order_by="nope")

    def test_computed_temporal_field_not_orderable(self, client):
        with pytest.raises(ValidationError, match="provenance-derived"):
            client.query("Specimen", order_by="created_at")

    def test_order_by_with_as_of_raises(self, client):
        with pytest.raises(ValidationError, match="as_of"):
            client.query("Specimen", order_by="age", as_of=FUTURE)

    def test_order_by_with_date_window_raises(self, client):
        with pytest.raises(ValidationError, match="date_from"):
            client.query("Specimen", order_by="age", date_from="2020-01-01")

    def test_invalid_order_dir_raises(self, client):
        with pytest.raises(ValidationError, match="order_dir"):
            client.query("Specimen", order_by="age", order_dir="sideways")


class TestCount:
    def test_count_matches_query_total(self, client):
        assert client.count("Specimen") == 4
        assert client.count("Specimen") == client.query("Specimen").total

    def test_count_with_filters(self, client):
        assert (
            client.count(
                "Specimen", filters=[{"field": "age", "op": "gt", "value": 50}]
            )
            == 2
        )

    def test_count_with_where_tree(self, client):
        where = {
            "or": [
                {"field": "is_tumor", "value": True},
                {"field": "age", "op": "gte", "value": 75},
            ]
        }
        assert client.count("Specimen", where=where) == 3

    def test_count_ignores_nothing_it_should_see(self, client):
        # Unknown flat-path field: zero rows (legacy #149), count agrees.
        assert client.count("Specimen", filters=[{"nope": "x"}]) == 0

    def test_count_as_of(self, client):
        assert client.count("Specimen", as_of=FUTURE) == 4

    def test_count_across_types_without_entity_type(self, client):
        assert client.count() == 4  # only Specimen rows exist


class TestFacetCounts:
    def test_buckets_ordered_by_count_then_value(self, client):
        # is_tumor: False×2 (s1,s3), True×2 (s2,s4) — tie → value order.
        assert client.facet_counts("Specimen", "is_tumor") == [
            (False, 2),
            (True, 2),
        ]

    def test_null_values_not_counted(self, client):
        buckets = client.facet_counts("Specimen", "age")
        assert buckets == [(45, 1), (60, 1), (75, 1)]  # s4's absent age: no bucket

    def test_facets_respect_filters(self, client):
        buckets = client.facet_counts(
            "Specimen",
            "is_tumor",
            filters=[{"field": "age", "op": "gte", "value": 60}],
        )
        assert buckets == [(False, 1), (True, 1)]

    def test_unknown_field_raises(self, client):
        with pytest.raises(ValidationError, match="facet_counts"):
            client.facet_counts("Specimen", "nope")

    def test_computed_temporal_field_raises(self, client):
        with pytest.raises(ValidationError, match="provenance-derived"):
            client.facet_counts("Specimen", "created_at")


class TestFieldRange:
    def test_min_max(self, client):
        assert client.field_range("Specimen", "age") == (45, 75)
        assert client.field_range("Specimen", "score") == (1.5, 3.5)
        assert client.field_range("Specimen", "collected_on") == (
            "2024-01-10",
            "2026-06-20",
        )

    def test_range_respects_filters(self, client):
        assert client.field_range(
            "Specimen", "age", filters=[{"field": "is_tumor", "value": False}]
        ) == (45, 75)
        assert client.field_range(
            "Specimen", "age", filters=[{"field": "is_tumor", "value": True}]
        ) == (60, 60)

    def test_empty_match_set_is_none_none(self, client):
        assert client.field_range(
            "Specimen", "age", filters=[{"field": "name", "value": "nobody"}]
        ) == (None, None)

    def test_unknown_field_raises(self, client):
        with pytest.raises(ValidationError, match="field_range"):
            client.field_range("Specimen", "nope")


class TestAvailabilityConsistency:
    """ADR-0007's pinned rule: every aggregate sees exactly what list
    queries see. ``entity_counts()`` (which counts unavailable entities)
    is explicitly NOT the model."""

    @pytest.fixture
    def with_unavailable(self, client):
        client.set_availability_bulk(
            entity_type="Specimen",
            entity_ids=["s3"],
            is_available=False,
            reason="test",
        )
        return client

    def test_count_excludes_unavailable(self, with_unavailable):
        c = with_unavailable
        assert c.count("Specimen") == 3
        assert c.count("Specimen") == c.query("Specimen").total

    def test_facets_exclude_unavailable(self, with_unavailable):
        assert with_unavailable.facet_counts("Specimen", "is_tumor") == [
            (True, 2),
            (False, 1),
        ]

    def test_range_excludes_unavailable(self, with_unavailable):
        assert with_unavailable.field_range("Specimen", "age") == (45, 60)

    def test_ordered_list_excludes_unavailable(self, with_unavailable):
        assert ordered_ids(with_unavailable, order_by="age") == ["s1", "s2", "s4"]


class TestAdapterContractDefaults:
    def test_entity_store_defaults_raise(self, registry):
        from mosaic.core.storage import EntityStore

        class Minimal(EntityStore):
            def create(self, entity):  # pragma: no cover - contract stub
                ...

            def read(self, entity_id):
                ...

            def update(self, entity):
                ...

            def delete(self, entity_id):
                ...

            def find(self, query, *, as_of=None):
                ...

            def findAll(self):
                ...

            def findBy(self, **kwargs):
                ...

            def search(self, query, entity_type, field_name, min_score=0.0, limit=100):
                ...

            def track_creation(self, entity, metadata):
                ...

            def track_update(self, entity, metadata):
                ...

            def track_deletion(self, entity_id, metadata):
                ...

            def search_capabilities(self):
                ...

        store = Minimal()
        with pytest.raises(NotImplementedError):
            store.count(Query())
        with pytest.raises(NotImplementedError):
            store.facet_counts(Query(), "f")
        with pytest.raises(NotImplementedError):
            store.field_range(Query(), "f")
