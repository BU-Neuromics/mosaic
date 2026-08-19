"""GraphQL aggregation & ordering surface (ADR-0007, issue #156).

Covers ``orderBy``/``orderDir`` on list queries (generated per-class
``<Class>OrderField`` enums, computed temporal fields excluded), the
``{plural}Count`` / ``{plural}FacetCounts`` / ``{plural}FieldRange`` roots,
and the coded-error contract (as-of gate, unknown/unaggregatable fields).
SDK-level semantics (NULLs last, availability consistency, tiebreak) are
covered in ``tests/core/test_aggregation_and_ordering.py``; these tests
pin the transport shapes.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def seeded(hippo_client):
    donors = [
        {"id": "d1", "name": "Ada", "sex": "female"},
        {"id": "d2", "name": "Ben", "sex": "male"},
        {"id": "d3", "name": "Cyd", "sex": "female"},
    ]
    for d in donors:
        hippo_client.put("Donor", d)
    samples = [
        {"id": "s1", "name": "S-A", "donor_id": "d1", "volume_ml": 3.5,
         "replicate_count": 2, "is_tumor": False},
        {"id": "s2", "name": "S-B", "donor_id": "d1", "volume_ml": 1.5,
         "replicate_count": 5, "is_tumor": True},
        {"id": "s3", "name": "S-C", "donor_id": "d2", "volume_ml": 9.0,
         "is_tumor": False},  # no replicate_count — NULLs-last target
    ]
    for s in samples:
        hippo_client.put("Sample", s)
    return hippo_client


class TestOrderBy:
    def test_order_by_enum_generated(self, seeded, gql):
        body = gql(
            """
            { __type(name: "SampleOrderField") { enumValues { name } } }
            """
        )
        names = {v["name"] for v in body["data"]["__type"]["enumValues"]}
        assert {"ID", "NAME", "VOLUME_ML", "REPLICATE_COUNT", "IS_TUMOR"} <= names
        # Computed temporal fields and reference/multivalued slots are not
        # orderable columns (ADR-0007).
        assert "CREATED_AT" not in names
        assert "DONOR_ID" not in names

    def test_multivalued_reference_not_orderable(self, seeded, gql):
        body = gql(
            """
            { __type(name: "StudyOrderField") { enumValues { name } } }
            """
        )
        names = {v["name"] for v in body["data"]["__type"]["enumValues"]}
        assert "SAMPLE_IDS" not in names
        assert "TITLE" in names

    def test_order_by_numeric_desc(self, seeded, gql):
        body = gql(
            """
            { samples(orderBy: VOLUME_ML, orderDir: DESC) {
                items { id } total } }
            """
        )
        page = body["data"]["samples"]
        assert [i["id"] for i in page["items"]] == ["s3", "s1", "s2"]
        assert page["total"] == 3

    def test_order_by_nulls_last_with_paging(self, seeded, gql):
        body = gql(
            """
            { samples(orderBy: REPLICATE_COUNT, limit: 2, offset: 1) {
                items { id } total limit offset } }
            """
        )
        page = body["data"]["samples"]
        # replicate_count asc: s1(2), s2(5), s3(NULL last) — page [1:3].
        assert [i["id"] for i in page["items"]] == ["s2", "s3"]
        assert page["total"] == 3

    def test_order_composes_with_where(self, seeded, gql):
        body = gql(
            """
            { samples(where: {isTumor: {eq: false}},
                      orderBy: VOLUME_ML, orderDir: DESC) {
                items { id } total } }
            """
        )
        page = body["data"]["samples"]
        assert [i["id"] for i in page["items"]] == ["s3", "s1"]
        assert page["total"] == 2

    def test_order_by_with_as_of_is_coded_error(self, seeded, gql):
        body = gql(
            """
            { samples(orderBy: VOLUME_ML, asOf: "2999-01-01T00:00:00+00:00") {
                items { id } } }
            """
        )
        assert body["errors"][0]["extensions"]["code"] == (
            "ASOF_ORDERING_UNSUPPORTED"
        )


class TestCount:
    def test_count_matches_list_total(self, seeded, gql):
        body = gql("{ samplesCount donorsCount }")
        assert body["data"]["samplesCount"] == 3
        assert body["data"]["donorsCount"] == 3

    def test_count_with_filters_and_where(self, seeded, gql):
        body = gql(
            """
            { samplesCount(
                filters: [{field: "donor_id", value: "d1"}],
                where: {isTumor: {eq: false}}) }
            """
        )
        assert body["data"]["samplesCount"] == 1

    def test_count_under_as_of(self, seeded, gql):
        body = gql(
            """
            { samplesCount(asOf: "2999-01-01T00:00:00+00:00") }
            """
        )
        assert body["data"]["samplesCount"] == 3

    def test_count_rejects_unknown_filter_field(self, seeded, gql):
        body = gql(
            """
            { samplesCount(filters: [{field: "nope", value: 1}]) }
            """
        )
        assert body["errors"][0]["extensions"]["code"] == "UNKNOWN_FILTER_FIELD"


class TestFacetCounts:
    def test_buckets(self, seeded, gql):
        body = gql(
            """
            { donorsFacetCounts(field: "sex") { value count } }
            """
        )
        assert body["data"]["donorsFacetCounts"] == [
            {"value": "female", "count": 2},
            {"value": "male", "count": 1},
        ]

    def test_boolean_buckets_and_null_exclusion(self, seeded, gql):
        body = gql(
            """
            { samplesFacetCounts(field: "replicateCount") { value count } }
            """
        )
        # camelCase spelling accepted; s3's absent value is not a bucket.
        assert body["data"]["samplesFacetCounts"] == [
            {"value": 2, "count": 1},
            {"value": 5, "count": 1},
        ]

    def test_facets_respect_where(self, seeded, gql):
        body = gql(
            """
            { samplesFacetCounts(field: "isTumor",
                where: {volumeMl: {gt: 2.0}}) { value count } }
            """
        )
        assert body["data"]["samplesFacetCounts"] == [
            {"value": False, "count": 2},
        ]

    def test_unknown_field_is_coded_error(self, seeded, gql):
        body = gql('{ samplesFacetCounts(field: "nope") { value count } }')
        assert body["errors"][0]["extensions"]["code"] == (
            "UNKNOWN_AGGREGATION_FIELD"
        )

    def test_computed_temporal_field_is_coded_error(self, seeded, gql):
        body = gql('{ samplesFacetCounts(field: "createdAt") { value count } }')
        assert body["errors"][0]["extensions"]["code"] == "UNAGGREGATABLE_FIELD"

    def test_multivalued_reference_is_coded_error(self, seeded, gql):
        body = gql('{ studysFacetCounts(field: "sampleIds") { value count } }')
        assert body["errors"][0]["extensions"]["code"] == "UNAGGREGATABLE_FIELD"


class TestFieldRange:
    def test_numeric_range(self, seeded, gql):
        body = gql('{ samplesFieldRange(field: "volumeMl") { min max } }')
        assert body["data"]["samplesFieldRange"] == {"min": 1.5, "max": 9.0}

    def test_range_respects_filters(self, seeded, gql):
        body = gql(
            """
            { samplesFieldRange(field: "volumeMl",
                filters: [{field: "donor_id", value: "d1"}]) { min max } }
            """
        )
        assert body["data"]["samplesFieldRange"] == {"min": 1.5, "max": 3.5}

    def test_empty_match_set_is_null_null(self, seeded, gql):
        body = gql(
            """
            { samplesFieldRange(field: "volumeMl",
                where: {name: {eq: "nobody"}}) { min max } }
            """
        )
        assert body["data"]["samplesFieldRange"] == {"min": None, "max": None}

    def test_string_field_is_coded_error(self, seeded, gql):
        body = gql('{ samplesFieldRange(field: "name") { min max } }')
        assert body["errors"][0]["extensions"]["code"] == "UNAGGREGATABLE_FIELD"
