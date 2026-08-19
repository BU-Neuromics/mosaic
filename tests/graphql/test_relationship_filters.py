"""GraphQL to-one relationship predicates (ADR-0006 M5a, issue #155).

`<Type>Filter` nests the target type's filter under the to-one edge name;
the resolver walker emits the SDK's `{edge, where}` tree node. Covers the
transport shapes: nesting, self-reference, composition, the asOf gate
(`ASOF_RELATIONSHIP_FILTER_UNSUPPORTED`), empty-object and depth-cap
errors, and search composition. SDK semantics live in
``tests/core/test_relationship_predicates.py``.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def seeded(hippo_client):
    donors = [
        {"id": "d1", "name": "Ada", "sex": "female"},
        {"id": "d2", "name": "Ben", "sex": "male"},
    ]
    for d in donors:
        hippo_client.put("Donor", d)
    samples = [
        {"id": "s1", "name": "S1", "donor_id": "d1", "volume_ml": 3.5,
         "is_tumor": True, "notes": "cortex lesion"},
        {"id": "s2", "name": "S2", "donor_id": "d2", "volume_ml": 1.5,
         "is_tumor": False, "notes": "cortex intact"},
        {"id": "s3", "name": "S3", "donor_id": "d1", "volume_ml": 9.0,
         "is_tumor": False},
        {"id": "s4", "name": "S4", "parent": "s1", "volume_ml": 2.0,
         "is_tumor": False},
    ]
    for s in samples:
        hippo_client.put("Sample", s)
    return hippo_client


def _ids(page):
    return [i["id"] for i in page["items"]]


class TestToOneEdgeFilters:
    def test_edge_predicate_on_target_filter(self, seeded, gql):
        body = gql(
            """
            { samples(where: {donor: {sex: {eq: female}}}) {
                items { id } total } }
            """
        )
        page = body["data"]["samples"]
        assert _ids(page) == ["s1", "s3"]
        assert page["total"] == 2

    def test_edge_composes_with_scalar_fields(self, seeded, gql):
        body = gql(
            """
            { samples(where: {donor: {sex: {eq: female}},
                              isTumor: {eq: false}}) { items { id } } }
            """
        )
        assert _ids(body["data"]["samples"]) == ["s3"]

    def test_self_referential_edge(self, seeded, gql):
        body = gql(
            """
            { samples(where: {parent: {isTumor: {eq: true}}}) { items { id } } }
            """
        )
        assert _ids(body["data"]["samples"]) == ["s4"]

    def test_not_edge_is_two_valued(self, seeded, gql):
        # Entities without the reference satisfy the negation (s4).
        body = gql(
            """
            { samples(where: {not: {donor: {sex: {eq: female}}}}) {
                items { id } } }
            """
        )
        assert _ids(body["data"]["samples"]) == ["s2", "s4"]

    def test_search_composes_with_edge_filter(self, seeded, gql):
        body = gql(
            """
            { searchSamples(q: "cortex", where: {donor: {sex: {eq: female}}}) {
                items { id } total } }
            """
        )
        page = body["data"]["searchSamples"]
        assert _ids(page) == ["s1"]
        assert page["total"] == 1

    def test_count_with_edge_filter(self, seeded, gql):
        body = gql('{ samplesCount(where: {donor: {sex: {eq: female}}}) }')
        assert body["data"]["samplesCount"] == 2


class TestCodedErrors:
    def test_as_of_with_edge_is_coded_error(self, seeded, gql):
        body = gql(
            """
            { samples(where: {donor: {sex: {eq: female}}},
                      asOf: "2999-01-01T00:00:00+00:00") { items { id } } }
            """
        )
        assert body["errors"][0]["extensions"]["code"] == (
            "ASOF_RELATIONSHIP_FILTER_UNSUPPORTED"
        )

    def test_count_as_of_with_edge_is_coded_error(self, seeded, gql):
        body = gql(
            """
            { samplesCount(where: {donor: {sex: {eq: female}}},
                           asOf: "2999-01-01T00:00:00+00:00") }
            """
        )
        assert body["errors"][0]["extensions"]["code"] == (
            "ASOF_RELATIONSHIP_FILTER_UNSUPPORTED"
        )

    def test_scalar_where_under_as_of_still_works(self, seeded, gql):
        body = gql(
            """
            { samples(where: {isTumor: {eq: true}},
                      asOf: "2999-01-01T00:00:00+00:00") { items { id } } }
            """
        )
        assert "errors" not in body, body
        assert _ids(body["data"]["samples"]) == ["s1"]

    def test_empty_edge_object_is_invalid(self, seeded, gql):
        body = gql('{ samples(where: {donor: {}}) { items { id } } }')
        assert body["errors"][0]["extensions"]["code"] == "INVALID_FILTER_VALUE"

    def test_edge_nesting_counts_toward_depth_cap(self, seeded, gql):
        # 11 levels of parent-nesting exceeds MAX_WHERE_INPUT_DEPTH (10).
        inner = "{isTumor: {eq: true}}"
        for _ in range(11):
            inner = "{parent: %s}" % inner
        body = gql("{ samples(where: %s) { items { id } } }" % inner)
        assert body["errors"][0]["extensions"]["code"] == "FILTER_TOO_DEEP"

    def test_multivalued_reference_edge_not_offered(self, seeded, gql):
        # Study.sample_ids is relationship-backed multivalued: no edge
        # field on StudyFilter until M5b — GraphQL validation rejects it.
        body = gql(
            '{ studys(where: {sampleIds: {title: {eq: "x"}}}) { items { id } } }'
        )
        assert body["errors"], body