"""GraphQL heterogeneous roots (issue #158): `searchAll` + `neighbors`.

Transport shapes for the two envelope roots — the SDK semantics (rank
merge, edge-store union, caps, as-of scoping) are pinned in
``tests/core/test_heterogeneous_roots.py``."""

from __future__ import annotations

import pytest


@pytest.fixture
def seeded(hippo_client):
    hippo_client.put("Donor", {"id": "d1", "name": "Ada", "sex": "female"})
    hippo_client.put("Sample", {"id": "s1", "name": "S1", "donor_id": "d1",
                                "notes": "cortex cortex lesion here"})
    hippo_client.put("Sample", {"id": "s2", "name": "S2",
                                "notes": "cortex intact tissue okay"})
    hippo_client.put("Study", {"id": "st1", "title": "Cortex Study"})
    hippo_client.relationships.relate("st1", "s1", "includes_sample")
    return hippo_client


class TestSearchAll:
    def test_heterogeneous_hits(self, seeded, gql):
        body = gql(
            """
            { searchAll(q: "cortex") {
                entityId entityType score data createdAt } }
            """
        )
        assert "errors" not in body, body
        hits = body["data"]["searchAll"]
        # Only Sample declares an FTS slot in this schema; ranked s1 > s2.
        assert [(h["entityType"], h["entityId"]) for h in hits] == [
            ("Sample", "s1"), ("Sample", "s2"),
        ]
        assert hits[0]["score"] >= hits[1]["score"] > 0
        assert hits[0]["data"]["name"] == "S1"
        assert hits[0]["createdAt"]

    def test_limit(self, seeded, gql):
        body = gql('{ searchAll(q: "cortex", limit: 1) { entityId } }')
        assert [h["entityId"] for h in body["data"]["searchAll"]] == ["s1"]

    def test_introspectable(self, seeded, gql):
        body = gql(
            """
            { __type(name: "Query") { fields { name } } }
            """
        )
        names = {f["name"] for f in body["data"]["__type"]["fields"]}
        assert {"searchAll", "neighbors"} <= names


class TestNeighbors:
    def test_subgraph_envelope_with_both_edge_stores(self, seeded, gql):
        body = gql(
            """
            { neighbors(id: "s1") {
                nodes { entityId entityType data }
                edges { source target type edgeSource }
                edgeSources notices } }
            """
        )
        assert "errors" not in body, body
        graph = body["data"]["neighbors"]
        edges = {(e["source"], e["target"], e["edgeSource"])
                 for e in graph["edges"]}
        assert ("s1", "d1", "COLUMN") in edges
        assert ("st1", "s1", "LINK_TABLE") in edges
        assert {n["entityId"] for n in graph["nodes"]} == {"s1", "d1", "st1"}
        assert set(graph["edgeSources"]) == {"LINK_TABLE", "COLUMN"}
        assert graph["notices"] == []

    def test_depth(self, seeded, gql):
        body = gql(
            '{ neighbors(id: "st1", depth: 2) { nodes { entityId } } }'
        )
        assert {n["entityId"] for n in body["data"]["neighbors"]["nodes"]} == {
            "st1", "s1", "d1",
        }

    def test_as_of_disclosure(self, seeded, gql):
        body = gql(
            """
            { neighbors(id: "s1", asOf: "2999-01-01T00:00:00+00:00") {
                edges { edgeSource } edgeSources notices } }
            """
        )
        graph = body["data"]["neighbors"]
        assert graph["edgeSources"] == ["LINK_TABLE"]
        assert any("hippo#71" in n for n in graph["notices"])
        assert all(e["edgeSource"] == "LINK_TABLE" for e in graph["edges"])

    def test_unknown_id_is_not_found(self, seeded, gql):
        body = gql('{ neighbors(id: "nope") { nodes { entityId } } }')
        assert body["errors"][0]["extensions"]["code"] == "NOT_FOUND"
