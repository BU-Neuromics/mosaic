"""MCP server construction: the schema/capability resources (ADR-0009
decision 1, issue #182), the ``validate_query_spec``/``execute_query_spec``
tools (ADR-0009 decision 3, issue #183), and the ``construct-query-spec``
prompt (ADR-0009 decision 4, issue #184). Built once, at mount time, from
a ``MosaicClient``'s ``SchemaRegistry`` — no new data-access path
(ADR-0009: "sharing the same MosaicClient/SchemaRegistry every other
transport already uses").

The two resources are pure functions of the deployment's schema, not
per-request state, so — unlike GraphQL's resolvers, and unlike the two
tools — there is no per-request client lookup for them at all (the SDK's
static/non-templated resources cannot take a ``Context`` parameter in
the first place; see :func:`create_mcp_server`'s docstring). The tools DO
read live data, so they take ``ctx: Context`` and resolve
``request.app.state.hippo_client`` the same way GraphQL's
``context_getter`` does, falling back to the construction-time client.
The prompt is static text (like the resources) — it carries no schema
data of its own, only procedural guidance about the artifact's semantics.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Optional

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations

from mosaic.core.client import MosaicClient
from mosaic.core.exceptions import ConfigError
from mosaic.core.exceptions import ValidationError as MosaicValidationError
from mosaic.core.query_spec import (
    QuerySpecError,
    QuerySpecShapeError,
    parse_query_spec,
    validate_query_spec as _validate_query_spec,
)
from mosaic.core.query_spec_compiler import compile_query_spec
from mosaic.core.schema_typing import (
    EntityCapability,
    build_capability_manifest,
    build_type_model,
)
from mosaic.mcp.serialize import entity_capability_to_dict, entity_type_model_to_dict

#: Mirrors REST's list_entities bound (Query(..., ge=1, le=1000)) — this
#: surface is reachable by less-trusted automated clients than REST's
#: typical consumers, so rejecting an unreasonable limit loudly (not
#: silently clamping it) matches issue #129's "loud over wrong" rule.
MAX_EXECUTE_LIMIT = 1000


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

    def _client_from_context(ctx: Context, fallback: MosaicClient) -> MosaicClient:
        """Same client source as GraphQL's context_getter: the app-state
        client injected by create_default_app, falling back to the
        construction-time client (e.g. the in-memory test transport,
        which carries no HTTP request at all)."""
        request = getattr(ctx.request_context, "request", None)
        app = getattr(request, "app", None)
        state = getattr(app, "state", None)
        client = getattr(state, "hippo_client", None) if state is not None else None
        return client or fallback

    def _manifest_for(client: MosaicClient) -> dict[str, EntityCapability]:
        if client.registry is registry:
            return capability_manifest
        return build_capability_manifest(client.registry)

    def _error_dict(e: QuerySpecError) -> dict[str, Any]:
        return asdict(e)

    def _shape_error_dict(exc: QuerySpecShapeError) -> dict[str, Any]:
        return {"code": exc.code, "message": str(exc), "path": exc.path}

    @mcp.tool(
        annotations=ToolAnnotations(read_only_hint=True),
        description=(
            "Validate a QuerySpec (ADR-0009/ADR-0035) against this "
            "deployment's actual capabilities — anchor/slot/op/edge/enum-"
            "value/sort-field legality, all checked against mosaic://"
            "capabilities. Returns {valid, errors}; each error names the "
            "offending path and, for op/enum mismatches, the valid set. "
            "Never executes anything — call this before execute_query_spec, "
            "or standalone to check a QuerySpec without running it."
        ),
    )
    def validate_query_spec(query_spec: dict, ctx: Context) -> dict[str, Any]:
        client = _client_from_context(ctx, hippo_client)
        try:
            spec = parse_query_spec(query_spec)
        except QuerySpecShapeError as exc:
            return {"valid": False, "errors": [_shape_error_dict(exc)]}
        result = _validate_query_spec(spec, _manifest_for(client))
        return {"valid": result.valid, "errors": [_error_dict(e) for e in result.errors]}

    @mcp.tool(
        annotations=ToolAnnotations(read_only_hint=True),
        description=(
            "Validate a QuerySpec, then execute it if valid (ADR-0009): "
            "compiles to Mosaic's where:/order_by query surface and runs "
            "it through the same MosaicClient REST/GraphQL use. Always "
            "validates first — an invalid QuerySpec returns {valid: "
            "false, errors: [...]} with no items, exactly like "
            "validate_query_spec, so a client can validate-fix-retry with "
            "this one tool alone. Read-only: no write or mutation path "
            "exists on this surface."
        ),
    )
    def execute_query_spec(
        query_spec: dict, ctx: Context, limit: int = 100, offset: int = 0
    ) -> dict[str, Any]:
        client = _client_from_context(ctx, hippo_client)
        manifest = _manifest_for(client)
        if not (1 <= limit <= MAX_EXECUTE_LIMIT):
            return {
                "valid": False,
                "errors": [
                    {
                        "code": "INVALID_LIMIT",
                        "message": f"'limit' must be between 1 and {MAX_EXECUTE_LIMIT} "
                        f"(matches REST's list_entities bound), got {limit}",
                        "path": "$.limit",
                    }
                ],
                "items": None,
                "total": None,
            }
        if offset < 0:
            return {
                "valid": False,
                "errors": [
                    {"code": "INVALID_OFFSET", "message": "'offset' must be >= 0", "path": "$.offset"}
                ],
                "items": None,
                "total": None,
            }
        try:
            spec = parse_query_spec(query_spec)
        except QuerySpecShapeError as exc:
            return {"valid": False, "errors": [_shape_error_dict(exc)], "items": None, "total": None}
        result = _validate_query_spec(spec, manifest)
        if not result.valid:
            return {
                "valid": False,
                "errors": [_error_dict(e) for e in result.errors],
                "items": None,
                "total": None,
            }
        compiled = compile_query_spec(spec, manifest)
        try:
            page = client.query(
                entity_type=compiled.entity_type,
                where=compiled.where,
                as_of=compiled.as_of,
                order_by=compiled.order_by,
                order_dir=compiled.order_dir,
                limit=limit,
                offset=offset,
            )
        except MosaicValidationError as exc:
            # A validated QuerySpec should always compile cleanly — this
            # is a compiler/validator bug, not a query-time condition, but
            # it still comes back coded rather than as a bare traceback
            # (ADR-0009 item 3: actionable errors are load-bearing).
            return {
                "valid": False,
                "errors": [{"code": "COMPILE_ERROR", "message": str(exc), "path": "$"}],
                "items": None,
                "total": None,
            }
        dumped = page.model_dump(mode="json")
        return {"valid": True, "errors": [], "items": dumped["items"], "total": dumped["total"]}

    @mcp.prompt(
        title="Construct a Mosaic QuerySpec",
        description=(
            "Procedural guidance for building a valid QuerySpec (ADR-0009 "
            "decision 4) -- the semantics mosaic://schema and mosaic://"
            "capabilities don't convey on their own. Without this, every "
            "client independently reinvents (or fails to reinvent) this "
            "knowledge; this is the 'how to use it' layer on top of "
            "mosaic://capabilities' 'what exists'."
        ),
    )
    def construct_query_spec(goal: str = "") -> str:
        header = f"Build a QuerySpec for: {goal}\n\n" if goal else ""
        return header + _CONSTRUCT_QUERY_SPEC_GUIDANCE

    return mcp


_CONSTRUCT_QUERY_SPEC_GUIDANCE = """\
How to build a QuerySpec Mosaic will accept (ADR-0009/ADR-0035):

1. Check mosaic://capabilities FIRST. Every anchor/slot/op/edge below must \
come from there -- this guidance tells you the shape, capabilities tells \
you what a specific deployment actually has.

2. Field names are LinkML slot names -- snake_case, exactly as they \
appear in mosaic://schema/mosaic://capabilities. Never invent a \
camelCase rename.

3. A field with kind "reference" NEVER takes a direct filter op (an \
empty filter_ops list on it is not a bug -- check its `predicate` flag \
instead). Express relationship existence/predicates as ONE \
RelatedCondition: {"kind": "related", "edge": <the reference field's \
name>, "quantifier": "some" | "none", "criteria": [FieldCondition, ...]}. \
"some" = at least one match; "none" = no match -- this works uniformly \
whether the relationship is one-to-one or one-to-many, so never simulate \
it with a client-side per-id fan-out (fetch-then-filter in a loop).

4. `columns` is NOT supported yet -- omit it entirely. execute_query_spec \
always returns full entity envelopes; there is no column-projection or \
aggregate-vs-explode compiler on this deployment.

5. `asOf` cannot combine with a RelatedCondition anywhere in `criteria` \
(including nested inside a group) -- pick a point in time OR a \
relationship predicate, not both, on the same QuerySpec.

6. `sort` takes at most ONE field -- Mosaic's query surface has no \
multi-column sort to compile a second entry against.

7. An enum-kind field's value must be one of its exact enum_values -- \
check mosaic://capabilities/mosaic://schema, don't guess a value.

8. Minimal shape: {"v": 1, "anchor": <an exposed entity type>, "mode": \
"AND" | "OR", "criteria": [...]}. `asOf` and `sort` are optional \
top-level additions.

Workflow: call validate_query_spec first if you want to check a draft \
without running it; call execute_query_spec once you're ready to fetch \
results -- it validates internally too, and returns the exact same \
{valid, errors} shape (plus items/total) if something's still wrong, so \
you can read the error, fix the one thing it names, and retry."""


def _mosaic_version() -> str:
    from mosaic import __version__

    return __version__
