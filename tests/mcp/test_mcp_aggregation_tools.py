"""Tests for count_query_spec/facet_query_spec/field_range_query_spec
(issue #195): the MCP boundary's aggregation surface.

Ground truth here is `MosaicClient.count`/`facet_counts`/`field_range`
directly -- the same object every transport (REST, GraphQL, MCP) calls --
so a passing test proves the tool is a faithful passthrough onto the
already-shipped ADR-0007 aggregation surface, not new query logic with its
own chance to disagree with what GraphQL already returns for the same
filter.
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
    d1 = hippo_client.create("Donor", {"name": "D1", "sex": "female"})
    d2 = hippo_client.create("Donor", {"name": "D2", "sex": "male"})
    d3 = hippo_client.create("Donor", {"name": "D3", "sex": "female"})
    hippo_client.create("Sample", {"name": "S1", "donor_id": d1["id"], "volume_ml": 5.0})
    hippo_client.create("Sample", {"name": "S2", "donor_id": d1["id"], "volume_ml": 15.0})
    hippo_client.create("Sample", {"name": "S3", "donor_id": d2["id"], "volume_ml": 25.0})
    return d1, d2, d3


async def _call_tool(server, name: str, args: dict) -> dict:
    async with Client(server) as client:
        result = await client.call_tool(name, args)
        (content,) = result.content
        return json.loads(content.text)


@pytest.mark.anyio
class TestCountQuerySpec:
    async def test_counts_matching_entities(self, hippo_client):
        _seed(hippo_client)
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(
            server,
            "count_query_spec",
            {"query_spec": {"v": 1, "anchor": "Sample", "mode": "AND", "criteria": []}},
        )
        assert payload == {"valid": True, "errors": [], "count": 3}

    async def test_count_matches_client_count_directly(self, hippo_client):
        # Ground truth: the same MosaicClient.count() every transport calls.
        _seed(hippo_client)
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(
            server,
            "count_query_spec",
            {
                "query_spec": {
                    "v": 1, "anchor": "Sample", "mode": "AND",
                    "criteria": [{"kind": "field", "slot": "volume_ml", "op": "gt", "value": 10.0}],
                }
            },
        )
        expected = hippo_client.count(
            entity_type="Sample", where={"field": "volume_ml", "op": "gt", "value": 10.0}
        )
        assert payload["count"] == expected == 2

    async def test_invalid_spec_returns_no_count(self, hippo_client):
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(
            server,
            "count_query_spec",
            {
                "query_spec": {
                    "v": 1, "anchor": "Sample", "mode": "AND",
                    "criteria": [{"kind": "field", "slot": "nope", "op": "eq", "value": 1}],
                }
            },
        )
        assert payload["valid"] is False
        assert payload["count"] is None
        assert payload["errors"][0]["code"] == "UNKNOWN_SLOT"

    async def test_sort_is_rejected(self, hippo_client):
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(
            server,
            "count_query_spec",
            {
                "query_spec": {
                    "v": 1, "anchor": "Sample", "mode": "AND", "criteria": [],
                    "sort": [{"slot": "volume_ml", "direction": "asc"}],
                }
            },
        )
        assert payload["valid"] is False
        assert payload["count"] is None
        assert payload["errors"][0]["code"] == "SORT_NOT_APPLICABLE"

    async def test_as_of_is_accepted_matching_client_count(self, hippo_client):
        # count() DOES support as_of (unlike facet_counts/field_range) --
        # confirm the tool doesn't reject it.
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(
            server,
            "count_query_spec",
            {"query_spec": {
                "v": 1, "anchor": "Sample", "mode": "AND", "criteria": [],
                "asOf": "2020-01-01T00:00:00+00:00",
            }},
        )
        assert payload["valid"] is True
        assert payload["count"] == 0  # nothing existed yet at that timestamp


@pytest.mark.anyio
class TestFacetQuerySpec:
    async def test_facets_by_enum_field(self, hippo_client):
        _seed(hippo_client)
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(
            server,
            "facet_query_spec",
            {
                "query_spec": {"v": 1, "anchor": "Donor", "mode": "AND", "criteria": []},
                "field": "sex",
            },
        )
        assert payload["valid"] is True
        assert sorted(payload["facets"], key=lambda f: f["value"]) == [
            {"value": "female", "count": 2},
            {"value": "male", "count": 1},
        ]

    async def test_matches_client_facet_counts_directly(self, hippo_client):
        _seed(hippo_client)
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(
            server,
            "facet_query_spec",
            {
                "query_spec": {"v": 1, "anchor": "Donor", "mode": "AND", "criteria": []},
                "field": "sex",
            },
        )
        expected = hippo_client.facet_counts("Donor", "sex")
        assert {(f["value"], f["count"]) for f in payload["facets"]} == set(expected)

    async def test_facets_compose_with_criteria(self, hippo_client):
        d1, d2, d3 = _seed(hippo_client)
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(
            server,
            "facet_query_spec",
            {
                "query_spec": {
                    "v": 1, "anchor": "Donor", "mode": "AND",
                    "criteria": [{"kind": "field", "slot": "name", "op": "neq", "value": "D3"}],
                },
                "field": "sex",
            },
        )
        assert sorted(payload["facets"], key=lambda f: f["value"]) == [
            {"value": "female", "count": 1},
            {"value": "male", "count": 1},
        ]

    async def test_unknown_field_is_a_coded_error(self, hippo_client):
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(
            server,
            "facet_query_spec",
            {
                "query_spec": {"v": 1, "anchor": "Donor", "mode": "AND", "criteria": []},
                "field": "nope",
            },
        )
        assert payload["valid"] is False
        assert payload["facets"] is None
        assert payload["errors"][0]["code"] == "UNKNOWN_AGGREGATION_FIELD"

    async def test_reference_field_is_not_aggregatable(self, hippo_client):
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(
            server,
            "facet_query_spec",
            {
                "query_spec": {"v": 1, "anchor": "Sample", "mode": "AND", "criteria": []},
                "field": "donor_id",
            },
        )
        assert payload["valid"] is False
        assert payload["errors"][0]["code"] == "UNAGGREGATABLE_FIELD"

    async def test_as_of_is_rejected(self, hippo_client):
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(
            server,
            "facet_query_spec",
            {
                "query_spec": {
                    "v": 1, "anchor": "Donor", "mode": "AND", "criteria": [],
                    "asOf": "2020-01-01T00:00:00+00:00",
                },
                "field": "sex",
            },
        )
        assert payload["valid"] is False
        assert payload["errors"][0]["code"] == "ASOF_NOT_SUPPORTED"

    async def test_invalid_spec_is_checked_before_the_field_argument(self, hippo_client):
        # An unknown anchor/criteria error should surface before ever
        # looking at `field` -- otherwise a client can't tell which is wrong.
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(
            server,
            "facet_query_spec",
            {
                "query_spec": {
                    "v": 1, "anchor": "Donor", "mode": "AND",
                    "criteria": [{"kind": "field", "slot": "nope", "op": "eq", "value": 1}],
                },
                "field": "also_nope",
            },
        )
        assert payload["errors"][0]["code"] == "UNKNOWN_SLOT"


@pytest.mark.anyio
class TestFieldRangeQuerySpec:
    async def test_range_of_a_numeric_field(self, hippo_client):
        _seed(hippo_client)
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(
            server,
            "field_range_query_spec",
            {
                "query_spec": {"v": 1, "anchor": "Sample", "mode": "AND", "criteria": []},
                "field": "volume_ml",
            },
        )
        assert payload == {"valid": True, "errors": [], "min": 5.0, "max": 25.0}

    async def test_matches_client_field_range_directly(self, hippo_client):
        _seed(hippo_client)
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(
            server,
            "field_range_query_spec",
            {
                "query_spec": {"v": 1, "anchor": "Sample", "mode": "AND", "criteria": []},
                "field": "volume_ml",
            },
        )
        expected_min, expected_max = hippo_client.field_range("Sample", "volume_ml")
        assert (payload["min"], payload["max"]) == (expected_min, expected_max)

    async def test_no_matching_entity_is_a_valid_empty_result_not_an_error(self, hippo_client):
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(
            server,
            "field_range_query_spec",
            {
                "query_spec": {
                    "v": 1, "anchor": "Sample", "mode": "AND",
                    "criteria": [{"kind": "field", "slot": "name", "op": "eq", "value": "nonexistent"}],
                },
                "field": "volume_ml",
            },
        )
        assert payload == {"valid": True, "errors": [], "min": None, "max": None}

    async def test_string_field_is_not_range_queryable(self, hippo_client):
        # A string CAN be aggregatable (facetable) without being ordered/
        # range-queryable -- distinct capability flags on the same field.
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(
            server,
            "field_range_query_spec",
            {
                "query_spec": {"v": 1, "anchor": "Sample", "mode": "AND", "criteria": []},
                "field": "name",
            },
        )
        assert payload["valid"] is False
        assert payload["errors"][0]["code"] == "UNAGGREGATABLE_FIELD"

    async def test_sort_and_as_of_are_both_rejected(self, hippo_client):
        server = create_mcp_server(hippo_client)
        for extra, code in (
            ({"sort": [{"slot": "volume_ml"}]}, "SORT_NOT_APPLICABLE"),
            ({"asOf": "2020-01-01T00:00:00+00:00"}, "ASOF_NOT_SUPPORTED"),
        ):
            payload = await _call_tool(
                server,
                "field_range_query_spec",
                {
                    "query_spec": {"v": 1, "anchor": "Sample", "mode": "AND", "criteria": [], **extra},
                    "field": "volume_ml",
                },
            )
            assert payload["valid"] is False, extra
            assert payload["errors"][0]["code"] == code, extra


@pytest.mark.anyio
class TestAggregationToolsAreRegistered:
    async def test_all_three_tools_are_listed(self, hippo_client):
        async with Client(create_mcp_server(hippo_client)) as client:
            names = {t.name for t in (await client.list_tools()).tools}
            assert {"count_query_spec", "facet_query_spec", "field_range_query_spec"} <= names

    async def test_construct_query_spec_prompt_routes_counting_questions_to_the_new_tools(
        self, hippo_client
    ):
        # Regression against the exact silent-degradation failure mode
        # found downstream (mosaic-demo-small's Exon migration): asked for
        # a per-cohort facet count, the old prompt gave no guidance against
        # answering with a sorted row list instead.
        async with Client(create_mcp_server(hippo_client)) as client:
            result = await client.get_prompt("construct_query_spec", {})
            text = result.messages[0].content.text
            assert "facet_query_spec" in text
            assert "count_query_spec" in text
            assert "field_range_query_spec" in text
            assert "not an answer to a counting question" in text
