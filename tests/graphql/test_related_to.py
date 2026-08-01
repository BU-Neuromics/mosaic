"""GraphQL coverage for the `relatedTo` reverse-lookup query (issue #146).

Relationships-table-backed multivalued references (ADR-0002) resolve
forward through the ordinary edge field (e.g. `Study.samples`), but there
was no way to ask the reverse question — "what points at this entity" —
through GraphQL. `relatedTo` answers it via a thin delegation to
`RelationshipManager.find_relationships(target_id=...)`.

Uses the shared `Study.sample_ids -> Sample` multivalued reference slot
from `tests/graphql/conftest.py`.
"""

from __future__ import annotations


def test_related_to_finds_referencing_entity(gql):
    sample = gql(
        'mutation { createSample(data: {name: "s1"}) { id } }'
    )["data"]["createSample"]
    study = gql(
        """
        mutation($sampleIds: [ID!]) {
          createStudy(data: {title: "Study A", sampleIds: $sampleIds}) { id }
        }
        """,
        {"sampleIds": [sample["id"]]},
    )["data"]["createStudy"]

    result = gql(
        """
        query($id: ID!) {
          relatedTo(id: $id) {
            entityId
            entityType
            relationshipType
            data
          }
        }
        """,
        {"id": sample["id"]},
    )
    assert result.get("errors") is None, result
    related = result["data"]["relatedTo"]
    assert len(related) == 1
    assert related[0]["entityId"] == study["id"]
    assert related[0]["entityType"] == "Study"
    assert related[0]["relationshipType"] == "sample_ids"
    assert related[0]["data"]["title"] == "Study A"


def test_related_to_filters_by_relationship_type(gql):
    sample = gql(
        'mutation { createSample(data: {name: "s2"}) { id } }'
    )["data"]["createSample"]
    gql(
        """
        mutation($sampleIds: [ID!]) {
          createStudy(data: {title: "Study B", sampleIds: $sampleIds}) { id }
        }
        """,
        {"sampleIds": [sample["id"]]},
    )

    matching = gql(
        """
        query($id: ID!) {
          relatedTo(id: $id, relationshipType: "sample_ids") { entityId }
        }
        """,
        {"id": sample["id"]},
    )
    assert len(matching["data"]["relatedTo"]) == 1

    non_matching = gql(
        """
        query($id: ID!) {
          relatedTo(id: $id, relationshipType: "not_a_real_slot") { entityId }
        }
        """,
        {"id": sample["id"]},
    )
    assert non_matching["data"]["relatedTo"] == []


def test_related_to_unreferenced_entity_is_empty(gql):
    sample = gql(
        'mutation { createSample(data: {name: "lonely"}) { id } }'
    )["data"]["createSample"]

    result = gql(
        'query($id: ID!) { relatedTo(id: $id) { entityId } }',
        {"id": sample["id"]},
    )
    assert result.get("errors") is None, result
    assert result["data"]["relatedTo"] == []
