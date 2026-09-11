"""The issue #204 scenario end to end over the MCP boundary (ADR-0011).

``Donor.samples: {range: Sample, multivalued: true, inverse: donor_id}`` is
what a reverse-edge-aware planner would emit as ``anchor: Donor``,
``edge: samples``. With the inverse slot declared, the capability manifest
advertises it (with ``inverse_of``), ``validate_query_spec`` accepts it,
and ``execute_query_spec``/``count_query_spec`` answer through the
storage layer's reverse-FK path — no validator or compiler change.
"""

from __future__ import annotations

import json

import pytest
from mcp.client.client import Client

from mosaic.linkml_bridge import SchemaRegistry
from mosaic.mcp.server import create_mcp_server

from tests.mcp.conftest import MCP_TEST_SCHEMA

INVERSE_SCHEMA = MCP_TEST_SCHEMA.replace(
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


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry.from_yaml(INVERSE_SCHEMA)


async def _read_json(server, uri: str) -> dict:
    async with Client(server) as client:
        result = await client.read_resource(uri)
        (content,) = result.contents
        return json.loads(content.text)


async def _call_tool(server, name: str, args: dict) -> dict:
    async with Client(server) as client:
        result = await client.call_tool(name, args)
        (content,) = result.content
        return json.loads(content.text)


def _seed(hippo_client):
    hippo_client.put("Donor", {"id": "d1", "name": "D1", "sex": "female"})
    hippo_client.put("Donor", {"id": "d2", "name": "D2", "sex": "male"})
    hippo_client.put("Donor", {"id": "d3", "name": "D3", "sex": "unknown"})
    hippo_client.put("Sample", {"id": "s1", "name": "S1", "donor_id": "d1", "volume_ml": 5.0})
    hippo_client.put("Sample", {"id": "s2", "name": "S2", "donor_id": "d1", "volume_ml": 15.0})
    hippo_client.put("Sample", {"id": "s3", "name": "S3", "donor_id": "d2", "volume_ml": 25.0})


def _reverse_spec(quantifier: str = "some", criteria=None) -> dict:
    return {
        "v": 1,
        "anchor": "Donor",
        "mode": "AND",
        "criteria": [
            {
                "kind": "related",
                "edge": "samples",
                "quantifier": quantifier,
                "criteria": criteria
                if criteria is not None
                else [{"kind": "field", "slot": "volume_ml", "op": "gte", "value": 10.0}],
            }
        ],
    }


@pytest.mark.anyio
class TestInverseSlotOverMcp:
    async def test_capabilities_advertise_the_reverse_edge(self, hippo_client):
        server = create_mcp_server(hippo_client)
        payload = await _read_json(server, "mosaic://capabilities")
        samples = next(f for f in payload["Donor"]["fields"] if f["name"] == "samples")
        assert samples["kind"] == "reference"
        assert samples["multivalued"] is True
        assert samples["target_entity_type"] == "Sample"
        assert samples["predicate"] is True
        assert samples["filter_ops"] == []
        assert samples["inverse_of"] == "donor_id"
        donor_id = next(f for f in payload["Sample"]["fields"] if f["name"] == "donor_id")
        assert donor_id["inverse_of"] is None

    async def test_validate_accepts_the_issue_204_repro(self, hippo_client):
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(server, "validate_query_spec", {"query_spec": _reverse_spec()})
        assert payload == {"valid": True, "errors": []}

    async def test_execute_returns_the_donors_of_those_samples(self, hippo_client):
        _seed(hippo_client)
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(server, "execute_query_spec", {"query_spec": _reverse_spec()})
        assert payload["valid"] is True, payload
        assert {i["id"] for i in payload["items"]} == {"d1", "d2"}
        assert payload["total"] == 2

    async def test_none_quantifier_is_the_complement(self, hippo_client):
        _seed(hippo_client)
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(server, "execute_query_spec", {"query_spec": _reverse_spec("none")})
        assert {i["id"] for i in payload["items"]} == {"d3"}

    async def test_count_query_spec_agrees(self, hippo_client):
        _seed(hippo_client)
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(server, "count_query_spec", {"query_spec": _reverse_spec()})
        assert payload == {"valid": True, "errors": [], "count": 2}

    async def test_hydrated_rows_carry_the_derived_list(self, hippo_client):
        _seed(hippo_client)
        server = create_mcp_server(hippo_client)
        payload = await _call_tool(
            server,
            "execute_query_spec",
            {"query_spec": {"v": 1, "anchor": "Donor", "mode": "AND", "criteria": [
                {"kind": "field", "slot": "id", "op": "eq", "value": "d1"}]}},
        )
        (row,) = payload["items"]
        assert row["data"]["samples"] == ["s1", "s2"]

    async def test_reverse_edge_on_a_schema_without_inverse_still_fails_clearly(self, hippo_client):
        # Sanity: the *default* MCP fixture schema has no inverse slot, so
        # the identical spec must keep producing the coded UNKNOWN_EDGE
        # the issue reports — the fix is opt-in via the schema.
        from mosaic.core.client import MosaicClient
        from mosaic.core.query_spec import parse_query_spec, validate_query_spec
        from mosaic.core.schema_typing import build_capability_manifest

        plain = build_capability_manifest(SchemaRegistry.from_yaml(MCP_TEST_SCHEMA))
        result = validate_query_spec(parse_query_spec(_reverse_spec()), plain)
        assert [e.code for e in result.errors] == ["UNKNOWN_EDGE"]
        assert isinstance(hippo_client, MosaicClient)
