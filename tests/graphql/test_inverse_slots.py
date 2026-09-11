"""GraphQL surface for ``inverse``-declared slots (ADR-0011 / issue #204).

The type model exposes ``Donor.samples`` (inverse of ``Sample.donor_id``) as
an ordinary multivalued reference, so the generated schema grows a
``samples: [Sample!]`` edge, a ``samplesCount`` field and a
``DonorFilter.samples: {some, none}`` quantifier — all served through the
storage layer's reverse-FK path. The one GraphQL-specific rule is that the
derived slot is **not writable**: it is absent from Create/Update inputs.
"""

from __future__ import annotations

import pytest

from mosaic.linkml_bridge import SchemaRegistry

from tests.graphql.conftest import GRAPHQL_TEST_SCHEMA

INVERSE_SCHEMA = GRAPHQL_TEST_SCHEMA.replace(
    """      sex:
        range: SexEnum
""",
    """      sex:
        range: SexEnum
      samples:
        range: Sample
        multivalued: true
        inverse: donor_id
""",
)


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    # Module-level override of the package fixture: same schema plus the
    # inverse slot, so every downstream fixture (client, gql) picks it up.
    return SchemaRegistry.from_yaml(INVERSE_SCHEMA)


@pytest.fixture
def seeded(hippo_client):
    hippo_client.put("Donor", {"id": "d1", "name": "D1", "sex": "female"})
    hippo_client.put("Donor", {"id": "d2", "name": "D2", "sex": "male"})
    hippo_client.put("Donor", {"id": "d3", "name": "D3"})
    hippo_client.put("Sample", {"id": "s1", "name": "S1", "donor_id": "d1", "is_tumor": True, "volume_ml": 1.0})
    hippo_client.put("Sample", {"id": "s2", "name": "S2", "donor_id": "d1", "is_tumor": False, "volume_ml": 2.0})
    hippo_client.put("Sample", {"id": "s3", "name": "S3", "donor_id": "d2", "is_tumor": True, "volume_ml": 3.0})
    return hippo_client


def _ids(page):
    return sorted(i["id"] for i in page["items"])


class TestReverseEdgeReads:
    def test_reverse_edge_resolves_to_the_referencing_samples(self, seeded, gql):
        body = gql('{ donor(id: "d1") { samples { id name } samplesCount } }')
        assert "errors" not in body, body
        donor = body["data"]["donor"]
        assert sorted(s["id"] for s in donor["samples"]) == ["s1", "s2"]
        assert donor["samplesCount"] == 2

    def test_donor_without_samples(self, seeded, gql):
        body = gql('{ donor(id: "d3") { samples { id } samplesCount } }')
        assert body["data"]["donor"] == {"samples": [], "samplesCount": 0}

    def test_count_excludes_unavailable_targets(self, seeded, gql):
        seeded.delete("Sample", "s1")
        body = gql('{ donor(id: "d1") { samplesCount samples { id } } }')
        donor = body["data"]["donor"]
        assert donor["samplesCount"] == 1
        assert [s["id"] for s in donor["samples"]] == ["s2"]

    def test_round_trip_back_through_the_forward_edge(self, seeded, gql):
        body = gql('{ donor(id: "d2") { samples { donor { id } } } }')
        assert body["data"]["donor"]["samples"] == [{"donor": {"id": "d2"}}]


class TestReverseEdgeFilter:
    def test_some(self, seeded, gql):
        body = gql("{ donors(where: {samples: {some: {isTumor: {eq: true}}}}) { items { id } } }")
        assert "errors" not in body, body
        assert _ids(body["data"]["donors"]) == ["d1", "d2"]

    def test_none_includes_sampleless(self, seeded, gql):
        body = gql("{ donors(where: {samples: {none: {isTumor: {eq: true}}}}) { items { id } } }")
        assert _ids(body["data"]["donors"]) == ["d3"]

    def test_some_composes_with_scalar(self, seeded, gql):
        body = gql(
            '{ donors(where: {sex: {eq: female}, samples: {some: {volumeMl: {gte: 2.0}}}}) '
            "{ total items { id } } }"
        )
        assert body["data"]["donors"]["total"] == 1
        assert _ids(body["data"]["donors"]) == ["d1"]

    def test_reverse_edge_nests_inside_the_forward_edge(self, seeded, gql):
        # Samples whose donor has some non-tumor sample: d1's samples.
        body = gql("{ samples(where: {donor: {samples: {some: {isTumor: {eq: false}}}}}) { items { id } } }")
        assert "errors" not in body, body
        assert _ids(body["data"]["samples"]) == ["s1", "s2"]


class TestNotWritable:
    def test_create_and_update_inputs_omit_the_derived_slot(self, gql):
        for input_name in ("DonorCreateInput", "DonorUpdateInput"):
            body = gql('{ __type(name: "%s") { inputFields { name } } }' % input_name)
            names = {f["name"] for f in body["data"]["__type"]["inputFields"]}
            assert "name" in names
            assert "samples" not in names, input_name

    def test_filter_input_still_carries_the_quantifier(self, gql):
        body = gql('{ __type(name: "DonorFilter") { inputFields { name type { name } } } }')
        fields = {f["name"]: f["type"]["name"] for f in body["data"]["__type"]["inputFields"]}
        assert "samples" in fields
