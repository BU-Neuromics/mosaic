"""GraphQL cardinality field for a multivalued reference edge (issue #132,
deferred from ADR-0005 — the interim resolve-to-count optimization).

Every resolvable multivalued reference field gets a `<field>Count: Int!`
sibling that answers the edge's cardinality without resolving any member
object — the relationship-count-badge consumer named in the issue. SDK
semantics (availability, loud errors) are pinned in
``tests/core/test_relationship_count.py``; these tests pin the transport
shape. The conftest schema's `Study.sample_ids` (multivalued -> Sample,
resolved as `samples`) is the edge under test.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def seeded(hippo_client):
    hippo_client.put("Sample", {"id": "s1", "name": "S1"})
    hippo_client.put("Sample", {"id": "s2", "name": "S2"})
    hippo_client.put("Sample", {"id": "s3", "name": "S3"})
    hippo_client.put("Study", {"id": "st1", "title": "Mixed",
                               "sample_ids": ["s1", "s2"]})
    hippo_client.put("Study", {"id": "st2", "title": "Empty"})
    return hippo_client


class TestSamplesCount:
    def test_count_matches_resolved_list_length(self, seeded, gql):
        body = gql(
            '{ study(id: "st1") { samplesCount samples { id } } }'
        )
        assert "errors" not in body, body
        study = body["data"]["study"]
        assert study["samplesCount"] == 2
        assert study["samplesCount"] == len(study["samples"])

    def test_count_without_requesting_the_list(self, seeded, gql):
        body = gql('{ study(id: "st1") { samplesCount } }')
        assert "errors" not in body, body
        assert body["data"]["study"]["samplesCount"] == 2

    def test_edgeless_entity_counts_zero(self, seeded, gql):
        body = gql('{ study(id: "st2") { samplesCount } }')
        assert "errors" not in body, body
        assert body["data"]["study"]["samplesCount"] == 0

    def test_unavailable_target_excluded(self, seeded, gql):
        seeded.set_availability_bulk(
            entity_type="Sample", entity_ids=["s2"],
            is_available=False, reason="test",
        )
        body = gql('{ study(id: "st1") { samplesCount } }')
        assert "errors" not in body, body
        assert body["data"]["study"]["samplesCount"] == 1

    def test_introspected_on_study_filter_type(self, seeded, gql):
        body = gql(
            '{ __type(name: "Study") { fields { name } } }'
        )
        names = {f["name"] for f in body["data"]["__type"]["fields"]}
        assert "samplesCount" in names
