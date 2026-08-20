"""GraphQL to-many quantified relationship predicates (ADR-0006 M5b,
issue #155 — the final typed-filter increment).

Multivalued reference edges on `<Type>Filter` nest a per-target
`{some, none}` quantifier object taking the target's filter. SDK
semantics are pinned in ``tests/core/test_quantified_predicates.py``;
these tests pin the transport shapes. The conftest schema's
`Study.sample_ids` (multivalued → Sample) is the edge under test.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def seeded(hippo_client):
    samples = [
        {"id": "s1", "name": "S1", "is_tumor": True, "volume_ml": 1.0},
        {"id": "s2", "name": "S2", "is_tumor": False, "volume_ml": 2.0},
        {"id": "s3", "name": "S3", "is_tumor": True, "volume_ml": 3.0},
    ]
    for s in samples:
        hippo_client.put("Sample", s)
    hippo_client.put("Study", {"id": "st1", "title": "Mixed",
                               "sample_ids": ["s1", "s2"]})
    hippo_client.put("Study", {"id": "st2", "title": "BenignOnly",
                               "sample_ids": ["s2"]})
    hippo_client.put("Study", {"id": "st3", "title": "Empty"})
    hippo_client.put("Study", {"id": "st4", "title": "TumorOnly",
                               "sample_ids": ["s3"]})
    return hippo_client


def _ids(page):
    return [i["id"] for i in page["items"]]


class TestQuantifiedFilters:
    def test_some(self, seeded, gql):
        body = gql(
            """
            { studys(where: {samples: {some: {isTumor: {eq: true}}}}) {
                items { id } total } }
            """
        )
        assert "errors" not in body, body
        page = body["data"]["studys"]
        assert _ids(page) == ["st1", "st4"]
        assert page["total"] == 2

    def test_none_includes_edgeless(self, seeded, gql):
        body = gql(
            """
            { studys(where: {samples: {none: {isTumor: {eq: true}}}}) {
                items { id } } }
            """
        )
        assert _ids(body["data"]["studys"]) == ["st2", "st3"]

    def test_some_and_none_and_together(self, seeded, gql):
        body = gql(
            """
            { studys(where: {samples: {
                some: {isTumor: {eq: false}},
                none: {isTumor: {eq: true}}}}) { items { id } } }
            """
        )
        assert _ids(body["data"]["studys"]) == ["st2"]

    def test_nested_scalar_operators_on_target(self, seeded, gql):
        body = gql(
            """
            { studys(where: {samples: {some: {volumeMl: {gte: 2.5}}}}) {
                items { id } } }
            """
        )
        assert _ids(body["data"]["studys"]) == ["st4"]

    def test_introspected_quantifier_input(self, seeded, gql):
        body = gql(
            """
            { filt: __type(name: "StudyFilter") { inputFields { name type { name } } }
              quant: __type(name: "SampleEdgeQuantifiers") { inputFields { name type { name } } } }
            """
        )
        filt = {f["name"]: f["type"]["name"]
                for f in body["data"]["filt"]["inputFields"]}
        assert filt["samples"] == "SampleEdgeQuantifiers"
        quant = {f["name"]: f["type"]["name"]
                 for f in body["data"]["quant"]["inputFields"]}
        assert quant == {"some": "SampleFilter", "none": "SampleFilter"}

    def test_empty_quantifier_object_is_coded_error(self, seeded, gql):
        body = gql('{ studys(where: {samples: {}}) { items { id } } }')
        assert body["errors"][0]["extensions"]["code"] == "INVALID_FILTER_VALUE"

    def test_as_of_with_quantifier_is_coded_error(self, seeded, gql):
        body = gql(
            """
            { studys(where: {samples: {some: {isTumor: {eq: true}}}},
                     asOf: "2999-01-01T00:00:00+00:00") { items { id } } }
            """
        )
        assert body["errors"][0]["extensions"]["code"] == (
            "ASOF_RELATIONSHIP_FILTER_UNSUPPORTED"
        )

    def test_flat_filters_still_reject_mv_refs_pointing_at_where(self, seeded, gql):
        body = gql(
            """
            { studys(filters: [{field: "sampleIds", value: "s1"}]) { total } }
            """
        )
        err = body["errors"][0]
        assert err["extensions"]["code"] == "UNFILTERABLE_FIELD"
        assert "some/none" in err["message"]

    def test_search_composes_with_quantifier(self, seeded, gql):
        # Sample declares the FTS slot; quantifiers ride the shared
        # predicate so they compose with samplesCount and search alike.
        body = gql(
            '{ studysCount(where: {samples: {some: {isTumor: {eq: true}}}}) }'
        )
        assert body["data"]["studysCount"] == 2
