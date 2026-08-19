"""GraphQL search composition (issue #157): search twins take the list
surface's filter arguments and return the Page envelope. Envelope shape
and the offset regression are pinned in ``test_parity.py``; these tests
pin the composition arguments and coded errors."""

from __future__ import annotations

import pytest


@pytest.fixture
def seeded(hippo_client):
    samples = [
        {"id": "s1", "name": "One", "volume_ml": 1.0, "is_tumor": False,
         "notes": "cortex cortex cortex alpha"},
        {"id": "s2", "name": "Two", "volume_ml": 2.0, "is_tumor": True,
         "notes": "cortex cortex beta filler"},
        {"id": "s3", "name": "Three", "volume_ml": 3.0, "is_tumor": False,
         "notes": "cortex gamma delta filler"},
        {"id": "s4", "name": "Four", "volume_ml": 4.0, "is_tumor": True,
         "notes": "hippocampus only here now"},
    ]
    for s in samples:
        hippo_client.put("Sample", s)
    return hippo_client


class TestSearchComposition:
    def test_rank_order_with_total(self, seeded, gql):
        body = gql('{ searchSamples(q: "cortex") { items { id } total } }')
        page = body["data"]["searchSamples"]
        assert [i["id"] for i in page["items"]] == ["s1", "s2", "s3"]
        assert page["total"] == 3

    def test_where_composes(self, seeded, gql):
        body = gql(
            """
            { searchSamples(q: "cortex", where: {isTumor: {eq: false}}) {
                items { id } total } }
            """
        )
        page = body["data"]["searchSamples"]
        assert [i["id"] for i in page["items"]] == ["s1", "s3"]
        assert page["total"] == 2

    def test_flat_filters_compose(self, seeded, gql):
        body = gql(
            """
            { searchSamples(q: "cortex",
                filters: [{field: "volumeMl", op: GTE, value: 2.0}]) {
                items { id } total } }
            """
        )
        page = body["data"]["searchSamples"]
        assert [i["id"] for i in page["items"]] == ["s2", "s3"]

    def test_order_by_overrides_rank(self, seeded, gql):
        body = gql(
            """
            { searchSamples(q: "cortex", orderBy: VOLUME_ML, orderDir: DESC) {
                items { id } total } }
            """
        )
        page = body["data"]["searchSamples"]
        assert [i["id"] for i in page["items"]] == ["s3", "s2", "s1"]
        assert page["total"] == 3

    def test_unknown_filter_field_is_coded_error(self, seeded, gql):
        body = gql(
            """
            { searchSamples(q: "cortex",
                filters: [{field: "nope", value: 1}]) { total } }
            """
        )
        assert body["errors"][0]["extensions"]["code"] == "UNKNOWN_FILTER_FIELD"

    def test_search_total_equals_count_under_same_criteria(self, seeded, gql):
        # The envelope's total honors the composed criteria with the same
        # availability rule as the aggregation surface.
        body = gql(
            """
            { searchSamples(q: "cortex", where: {isTumor: {eq: true}}) { total }
              samplesCount(where: {isTumor: {eq: true}}) }
            """
        )
        assert body["data"]["searchSamples"]["total"] == 1  # s2 only
        assert body["data"]["samplesCount"] == 2  # s2 and s4 — no FTS bound
