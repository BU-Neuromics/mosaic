"""Tests for search_query_spec (issue #196): full-text search on the MCP
boundary, composed with a QuerySpec's criteria.

Ground truth is `MosaicClient.search()` directly -- the same object
GraphQL's own `search{Plural}` resolvers call -- so a passing test proves
the tool is a faithful passthrough, including its documented quirk (a
non-searchable entity returns an empty result, not an error, on both
transports).
"""

from __future__ import annotations

import json

import pytest
from mcp.client.client import Client

from mosaic.mcp.server import create_mcp_server


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _seed(hippo_client):
    donor = hippo_client.create("Donor", {"name": "D1", "sex": "female"})
    hippo_client.create(
        "Sample", {"name": "Frontal cortex biopsy", "donor_id": donor["id"], "volume_ml": 5.0}
    )
    hippo_client.create(
        "Sample", {"name": "Cerebellum biopsy", "donor_id": donor["id"], "volume_ml": 15.0}
    )
    hippo_client.create(
        "Sample", {"name": "Unrelated blood draw", "donor_id": donor["id"], "volume_ml": 25.0}
    )
    return donor


async def _call_tool(server, name: str, args: dict) -> dict:
    async with Client(server) as client:
        result = await client.call_tool(name, args)
        (content,) = result.content
        return json.loads(content.text)


@pytest.mark.anyio
class TestSearchQuerySpec:
    async def test_searches_a_searchable_entity(self, hippo_client):
        _seed(hippo_client)
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(
            server,
            "search_query_spec",
            {"query_spec": {"v": 1, "anchor": "Sample", "mode": "AND", "criteria": []}, "q": "biopsy"},
        )
        assert payload["valid"] is True
        names = {item["data"]["name"] for item in payload["items"]}
        assert names == {"Frontal cortex biopsy", "Cerebellum biopsy"}
        assert payload["total"] == 2

    async def test_matches_client_search_directly(self, hippo_client):
        _seed(hippo_client)
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(
            server,
            "search_query_spec",
            {"query_spec": {"v": 1, "anchor": "Sample", "mode": "AND", "criteria": []}, "q": "biopsy"},
        )
        expected = hippo_client.search(entity_type="Sample", query="biopsy")
        assert payload["total"] == expected.total
        assert {i["data"]["name"] for i in payload["items"]} == {
            i["data"]["name"] for i in expected.model_dump(mode="json")["items"]
        }

    async def test_search_composes_with_criteria(self, hippo_client):
        _seed(hippo_client)
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(
            server,
            "search_query_spec",
            {
                "query_spec": {
                    "v": 1, "anchor": "Sample", "mode": "AND",
                    "criteria": [{"kind": "field", "slot": "volume_ml", "op": "gt", "value": 10.0}],
                },
                "q": "biopsy",
            },
        )
        assert payload["valid"] is True
        assert [item["data"]["name"] for item in payload["items"]] == ["Cerebellum biopsy"]

    async def test_non_searchable_entity_returns_empty_not_an_error(self, hippo_client):
        # Documented behavior (schema_typing.py's EntityCapability.search_available
        # docstring): Donor has no searchable slot in the test schema. GraphQL's own
        # searchDonors has the identical silent-empty behavior -- this tool must not
        # diverge from it by inventing a stricter gate on only one transport.
        _seed(hippo_client)
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(
            server,
            "search_query_spec",
            {"query_spec": {"v": 1, "anchor": "Donor", "mode": "AND", "criteria": []}, "q": "anything"},
        )
        assert payload == {"valid": True, "errors": [], "items": [], "total": 0}

    async def test_sort_overrides_fts_rank(self, hippo_client):
        _seed(hippo_client)
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(
            server,
            "search_query_spec",
            {
                "query_spec": {
                    "v": 1, "anchor": "Sample", "mode": "AND", "criteria": [],
                    "sort": [{"slot": "volume_ml", "direction": "desc"}],
                },
                "q": "biopsy",
            },
        )
        assert [item["data"]["name"] for item in payload["items"]] == [
            "Cerebellum biopsy", "Frontal cortex biopsy",
        ]

    async def test_as_of_is_rejected(self, hippo_client):
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(
            server,
            "search_query_spec",
            {
                "query_spec": {
                    "v": 1, "anchor": "Sample", "mode": "AND", "criteria": [],
                    "asOf": "2020-01-01T00:00:00+00:00",
                },
                "q": "biopsy",
            },
        )
        assert payload["valid"] is False
        assert payload["errors"][0]["code"] == "ASOF_NOT_SUPPORTED"

    async def test_invalid_spec_returns_no_items(self, hippo_client):
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(
            server,
            "search_query_spec",
            {
                "query_spec": {
                    "v": 1, "anchor": "Sample", "mode": "AND",
                    "criteria": [{"kind": "field", "slot": "nope", "op": "eq", "value": 1}],
                },
                "q": "biopsy",
            },
        )
        assert payload["valid"] is False
        assert payload["items"] is None
        assert payload["total"] is None
        assert payload["errors"][0]["code"] == "UNKNOWN_SLOT"

    async def test_limit_over_max_is_rejected_loudly(self, hippo_client):
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(
            server,
            "search_query_spec",
            {
                "query_spec": {"v": 1, "anchor": "Sample", "mode": "AND", "criteria": []},
                "q": "biopsy", "limit": 100000,
            },
        )
        assert payload["valid"] is False
        assert payload["errors"][0]["code"] == "INVALID_LIMIT"

    async def test_negative_offset_is_rejected(self, hippo_client):
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(
            server,
            "search_query_spec",
            {
                "query_spec": {"v": 1, "anchor": "Sample", "mode": "AND", "criteria": []},
                "q": "biopsy", "offset": -1,
            },
        )
        assert payload["valid"] is False
        assert payload["errors"][0]["code"] == "INVALID_OFFSET"


@pytest.mark.anyio
class TestSearchToolIsRegistered:
    async def test_tool_is_listed(self, hippo_client):
        async with Client(create_mcp_server(hippo_client)) as client:
            names = {t.name for t in (await client.list_tools()).tools}
            assert "search_query_spec" in names

    async def test_construct_query_spec_prompt_mentions_search(self, hippo_client):
        async with Client(create_mcp_server(hippo_client)) as client:
            result = await client.get_prompt("construct_query_spec", {})
            text = result.messages[0].content.text
            assert "search_query_spec" in text
            assert "search_available" in text
