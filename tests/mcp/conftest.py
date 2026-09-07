"""Shared fixtures for the MCP transport tests.

The whole package is skipped when the ``mcp`` package (the optional
``mcp`` extra) is not installed — mirrors ``tests/graphql``.
"""

from __future__ import annotations

import pytest

# Skip the entire package if the mcp SDK is not installed.
pytest.importorskip("mcp", reason="mcp not installed; run: pip install datahelix-mosaic[mcp]")

from mosaic.core.client import MosaicClient
from mosaic.linkml_bridge import SchemaRegistry
from mosaic.serve import create_default_app

# Reuses the exact fixture schema the GraphQL suite exercises (Donor/
# Sample/Study, a to-one and a to-many reference, an enum, a searchable
# slot) so the two transports' capability manifests are directly
# comparable in intent even though this package builds its own registry
# instance (session-scoped instances must not cross package boundaries).
MCP_TEST_SCHEMA = """
id: https://example.org/hippo/test_mcp
name: test_mcp
description: Schema exercising the MCP resource generation.
prefixes:
  linkml: https://w3id.org/linkml/
imports:
  - linkml:types
  - hippo_core
default_range: string

classes:
  Donor:
    is_a: Entity
    description: A tissue donor.
    attributes:
      name:
        required: true
      sex:
        range: SexEnum

  Sample:
    is_a: Entity
    attributes:
      name:
        required: true
        annotations:
          hippo_search: fts5
      donor_id:
        range: Donor
      volume_ml:
        range: float

enums:
  SexEnum:
    permissible_values:
      male: {}
      female: {}
      unknown: {}
"""


@pytest.fixture(scope="session")
def registry() -> SchemaRegistry:
    return SchemaRegistry.from_yaml(MCP_TEST_SCHEMA)


@pytest.fixture
def hippo_client(registry: SchemaRegistry) -> MosaicClient:
    return MosaicClient(registry=registry)


@pytest.fixture
def mcp_app(hippo_client: MosaicClient):
    return create_default_app(hippo_client=hippo_client, mcp=True)
