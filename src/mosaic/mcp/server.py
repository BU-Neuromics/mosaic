"""MCP server construction: the schema/capability resources (ADR-0009
decision 1, issue #182). Built once, at mount time, from a
``MosaicClient``'s ``SchemaRegistry`` — no new data-access path
(ADR-0009: "sharing the same MosaicClient/SchemaRegistry every other
transport already uses"). Both resources are pure functions of the
deployment's schema, not per-request state, so unlike GraphQL's
resolvers there is no per-request client lookup here at all — see
:func:`create_mcp_server`'s docstring for why.

**Scope note:** resources only. No ``validate_query_spec``/
``execute_query_spec`` tools and no ``construct-query-spec`` prompt —
those are #183's remaining half and #184, both separate increments.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from mosaic.core.client import MosaicClient
from mosaic.core.exceptions import ConfigError
from mosaic.core.schema_typing import build_capability_manifest, build_type_model
from mosaic.mcp.serialize import entity_capability_to_dict, entity_type_model_to_dict


def create_mcp_server(hippo_client: MosaicClient) -> MCPServer:
    """Build the MCP server for one Mosaic deployment.

    Both resources are pure functions of ``hippo_client.registry`` — a
    deployment's schema, not per-request state — so they are computed
    once, here, at mount time and served as static payloads (mirrors
    ``create_graphql_router``'s schema-at-mount-time split; the SDK's
    static/non-templated resources cannot take a ``Context`` parameter
    at all, so there is no per-request client lookup to do here). Unlike
    the schema/capability resources, a future ``execute_query_spec`` tool
    (#183's remaining half) DOES need the live ``app.state.hippo_client``
    per request, the same way GraphQL resolvers do.

    Raises:
        ConfigError: When ``hippo_client`` has no schema registry — both
            resources are computed from the deployment's LinkML schema.
    """
    registry = hippo_client.registry
    if registry is None:
        raise ConfigError(
            "MCP transport requires a schema-backed MosaicClient: both "
            "resources are computed from the deployment's LinkML schema. "
            "Construct the client with a SchemaRegistry (e.g. via "
            "`mosaic serve --mcp --config mosaic.yaml` with a config that "
            "names a schema_path)."
        )

    type_model = build_type_model(registry)
    capability_manifest = build_capability_manifest(registry)
    schema_payload = {name: entity_type_model_to_dict(e) for name, e in type_model.items()}
    capabilities_payload = {
        name: entity_capability_to_dict(e) for name, e in capability_manifest.items()
    }

    mcp = MCPServer(
        "mosaic",
        version=_mosaic_version(),
        instructions=(
            "Mosaic is a runtime for LinkML schemas: a typed SDK, REST API, "
            "and GraphQL surface over a schema-defined entity graph. Read "
            "mosaic://schema for the raw type model (every exposed entity "
            "type's fields, kinds, and relationships) and "
            "mosaic://capabilities for what the query boundary supports "
            "per field (filter operators, relationship-predicate "
            "filterability, orderable/aggregatable/range-queryable/"
            "searchable). This surface is read-only: no write or mutation "
            "tool exists here (ADR-0009)."
        ),
    )

    @mcp.resource(
        "mosaic://schema",
        name="schema",
        title="Mosaic entity type model",
        description=(
            "Every exposed entity type's fields, kinds (scalar/enum/"
            "reference), roles, and relationships — the raw LinkML type "
            "model (mirrors GraphQL's hippoSchema / REST's GET /schemas)."
        ),
        mime_type="application/json",
    )
    def schema_resource() -> dict[str, Any]:
        return schema_payload

    @mcp.resource(
        "mosaic://capabilities",
        name="capabilities",
        title="Mosaic query capability manifest",
        description=(
            "Per-field query capability (ADR-0009/#181): supported filter "
            "operators, relationship-predicate filterability, orderable/"
            "aggregatable/range-queryable/searchable flags. A reference "
            "field with an empty filter_ops list is not unfilterable -- "
            "check `predicate`; it is filtered via a RelatedCondition "
            "(nested edge), never a direct filter operator."
        ),
        mime_type="application/json",
    )
    def capabilities_resource() -> dict[str, Any]:
        return capabilities_payload

    return mcp


def _mosaic_version() -> str:
    from mosaic import __version__

    return __version__
