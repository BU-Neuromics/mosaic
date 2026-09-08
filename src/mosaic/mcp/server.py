"""MCP server construction: the schema/capability resources (ADR-0009
decision 1, issue #182), the ``validate_query_spec``/``execute_query_spec``
tools (ADR-0009 decision 3, issue #183), the ``count_query_spec``/
``facet_query_spec``/``field_range_query_spec`` tools (issue #195), the
``search_query_spec`` tool (issue #196), the ``converse_query_spec`` tool
(issue #186, registered only when ``MOSAIC_EXON_URL`` is set), and the
``construct-query-spec`` prompt (ADR-0009 decision 4, issue #184). Built
once, at mount time, from a ``MosaicClient``'s ``SchemaRegistry`` — no new
data-access path (ADR-0009: "sharing the same MosaicClient/SchemaRegistry
every other transport already uses").

The four non-execute tools exist because ``QuerySpec`` (ADR-0035) has no
representation for aggregation OR search — ``execute_query_spec`` can only
ever return rows. Mosaic's own aggregation/search surface (``count``/
``facet_counts``/``field_range``/``search``, ADR-0007/#157) was already
shipped for GraphQL; these tools are thin wrappers, not new query logic —
same ``compile_query_spec`` output, same ``MosaicClient`` methods GraphQL's
own resolvers call. Error codes (``UNKNOWN_AGGREGATION_FIELD``,
``UNAGGREGATABLE_FIELD``) are copied verbatim from ``graphql/resolvers.py``'s
``_resolve_aggregate_field`` so a client sees the same failure for the same
field regardless of transport. ``search_query_spec`` deliberately does NOT
add a stricter "is this searchable" gate GraphQL's own ``search{Plural}``
resolvers lack — a non-searchable entity returns an empty result on both
transports, by the same documented design (``schema_typing.py``'s
``EntityCapability.search_available`` docstring): inventing a gate on one
transport only would make the two answer the same call differently.

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

``converse_query_spec`` is the one tool here that is not a wrapper over a
``MosaicClient`` method: it delegates server-to-server to Exon's stateless
turn-taking planning core over HTTP (the wire contract is recorded in
``mosaic-demo-small``'s ``add-exon-conversational-contract/design.md``
Decision 8), because Aperture's browser has no backend of its own and must
not hold LLM credentials. It is registered ONLY when ``MOSAIC_EXON_URL``
names that service — an unconfigured deployment does not advertise a tool
it cannot serve, mirroring how ``--mcp`` itself gates this whole module.
Mosaic re-validates whatever ``QuerySpec`` Exon returns, in-process,
before ever handing back a ``proposal`` turn: Exon is an untrusted planner
as far as this boundary is concerned, and "Mosaic validates before
anything executes" has to hold even if Exon's own check is stale or
bypassed. It never calls ``execute_query_spec`` — a ``proposal`` is handed
back for a separate, explicit execute call once a human confirms it, so
"the LLM never decides to execute" holds for this tool too.
"""

from __future__ import annotations

import os
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

#: Env var naming Exon's conversational turn endpoint (issue #186). Unset
#: (or blank) means ``converse_query_spec`` is not registered at all —
#: same gating philosophy as ``--mcp``/``MOSAIC_SERVE_MCP`` for this
#: module: an optional integration is absent, not present-and-broken.
EXON_URL_ENV = "MOSAIC_EXON_URL"

#: Sized for the hosted-model latency this integration actually targets
#: (a conversational turn against Bedrock Haiku), NOT for slow local
#: generation. Deliberately not Exon's own ``REQUEST_TIMEOUT``, which is
#: tuned far higher for local/Ollama runs and would make a chat turn feel
#: hung rather than failed. Overridable for a deployment whose model is
#: slower, but the default should stay in "a person is waiting" territory.
EXON_TIMEOUT_ENV = "MOSAIC_EXON_TIMEOUT"
DEFAULT_EXON_TIMEOUT_SECONDS = 60.0

#: The turn statuses Exon itself may return (design.md Decision 8). Any
#: other value is treated as a malformed response, not passed through:
#: this envelope is what Aperture branches on, so an unrecognized status
#: reaching the UI would be a silent contract break.
_EXON_TURN_STATUSES = frozenset({"proposal", "clarification", "suspended"})


def _exon_timeout() -> float:
    """Read the Exon request timeout, falling back to the default on an
    unparseable or non-positive value rather than propagating a broken
    deployment config into per-request failures."""
    raw = os.environ.get(EXON_TIMEOUT_ENV, "").strip()
    if not raw:
        return DEFAULT_EXON_TIMEOUT_SECONDS
    try:
        parsed = float(raw)
    except ValueError:
        return DEFAULT_EXON_TIMEOUT_SECONDS
    return parsed if parsed > 0 else DEFAULT_EXON_TIMEOUT_SECONDS


def _reject_malformed_exon_response(body: Any) -> Optional[str]:
    """Check Exon's response against Decision 8's shape before trusting
    any of it, returning a human-readable reason or None.

    This is deliberately strict rather than duck-typed. Mosaic is the only
    thing standing between an out-of-contract planning service and
    Aperture's UI: a missing ``status``, an unrecognized one, or a
    ``clarification`` that smuggles a ``query_spec`` would each become a
    silent contract break downstream, where it is far harder to diagnose
    than here. Cheap to check, and it fails with the reason named.
    """
    if not isinstance(body, dict):
        return f"expected a JSON object, got {type(body).__name__}."
    turn = body.get("turn")
    if not isinstance(turn, dict):
        return "the response has no 'turn' object."
    problem = _reject_malformed_turn(turn)
    if problem:
        return f"the turn's {problem}" if problem.startswith("status") else problem
    suspended = body.get("suspended_turn_ids")
    if suspended is not None and not isinstance(suspended, list):
        return "'suspended_turn_ids' is present but not a list."

    # `turns` (the full post-call conversation) is optional for backward
    # compatibility, but when present every entry must satisfy the same
    # per-turn contract as `turn` -- these are handed straight to the caller,
    # and one malformed entry among them is no less a contract break than a
    # malformed `turn`.
    turns = body.get("turns")
    if turns is not None:
        if not isinstance(turns, list):
            return "'turns' is present but not a list."
        for i, t in enumerate(turns):
            if not isinstance(t, dict):
                return f"turns[{i}] is not an object."
            problem = _reject_malformed_turn(t)
            if problem:
                return f"turns[{i}]: {problem}"
    return None


def _reject_malformed_turn(turn: dict) -> Optional[str]:
    """Per-turn contract check, shared by `turn` and every `turns` entry."""
    status = turn.get("status")
    if status not in _EXON_TURN_STATUSES:
        return f"status {status!r} is not one of {sorted(_EXON_TURN_STATUSES)}."
    if not isinstance(turn.get("message"), str):
        return "no 'message' string."
    if status == "proposal":
        if not isinstance(turn.get("query_spec"), dict):
            return "a 'proposal' turn carries no 'query_spec' object."
    elif turn.get("query_spec") is not None:
        return (
            f"a {status!r} turn must carry query_spec: null, but one was "
            f"present -- only a 'proposal' changes the draft."
        )
    return None


def _error_turn(utterance: str, message: str) -> dict[str, Any]:
    """Decision 8's third top-level turn status. Exon unreachable, timed
    out, or a response that still fails Mosaic's re-validation all come
    back INSIDE the discriminated envelope Aperture already branches on,
    with ``query_spec: null`` — not as a bare MCP tool exception, which a
    chat UI would have no structured way to render next to the turns it
    already drew.

    The turn carries no ``id``: an ``error`` is not a conversational step
    Aperture can later rewind to or edit (there is nothing to recompute),
    so minting an id for it would invite exactly that misuse.

    Callers returning this deliberately OMIT ``turns`` rather than sending
    ``[]``. Every error path means nothing was applied, so the conversation
    is *unchanged* — and an empty list would say the opposite ("the
    conversation is now empty"), which a caller that replaces its state
    with the response would act on by wiping the chat. Absent means "no
    authoritative state supplied; keep your own."
    """
    return {
        "id": None,
        "utterance": utterance,
        "status": "error",
        "query_spec": None,
        "message": message,
    }


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

    # Described in `instructions` only when actually registered below --
    # advertising a tool an unconfigured deployment doesn't expose would
    # send a client looking for something that isn't in list_tools.
    _exon_configured = bool(os.environ.get(EXON_URL_ENV, "").strip())
    _exon_instructions = (
        " converse_query_spec builds a QuerySpec conversationally across "
        "turns (delegating to a configured planning service) and returns a "
        "proposal or a clarifying question; it never executes -- pass a "
        "proposal to execute_query_spec only on an explicit user action."
        if _exon_configured
        else ""
    )

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
            "searchable). execute_query_spec returns rows; count_query_spec/"
            "facet_query_spec/field_range_query_spec answer 'how many'/"
            "'how many per category'/'what's the min-max' WITHOUT rows -- "
            "use one of those instead of fetching rows and counting them "
            "yourself, and instead of trying to answer a counting question "
            "with a sorted row list (a QuerySpec has no aggregation shape "
            "of its own; these tools are the only way to get one). "
            "search_query_spec full-text searches an entity's searchable "
            "slots, composed with a QuerySpec's own criteria -- check "
            "search_available/searchable on mosaic://capabilities before "
            "calling it. This surface is read-only: no write or mutation "
            "tool exists here (ADR-0009)." + _exon_instructions
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

    def _reject_unsupported_for_aggregate(
        spec, *, allow_sort: bool = False, allow_as_of: bool
    ) -> Optional[dict[str, Any]]:
        """Not every QuerySpec field applies to every tool built on top of
        it, and which ones vary per underlying MosaicClient method's own
        signature -- not a rule this boundary invents:

        - `sort`: no meaning for a scalar/facet/range result (count/facet/
          range) -- GraphQL's own count/facetCounts/fieldRange resolvers
          expose no orderBy argument either. Meaningful for search (an
          explicit `sort` overrides FTS rank, matching `search()`'s own
          `order_by`), so `allow_sort=True` there.
        - `asOf`: supported only where the underlying method takes it --
          `count()` does; `facet_counts()`/`field_range()`/`search()` do
          not ("Not defined under as-of in this increment", their
          docstrings/module notes).

        Rejecting loudly here rather than silently dropping either follows
        issue #129's rule; validate_query_spec's own
        ASOF_RELATIONSHIP_FILTER_UNSUPPORTED check still runs underneath
        this for count_query_spec's asOf+RelatedCondition case."""
        if not allow_sort and spec.sort:
            return {
                "code": "SORT_NOT_APPLICABLE",
                "message": "'sort' has no effect on this aggregate result -- omit it",
                "path": "$.sort",
            }
        if not allow_as_of and spec.as_of is not None:
            return {
                "code": "ASOF_NOT_SUPPORTED",
                "message": (
                    "'asOf' is not supported here -- the underlying Mosaic "
                    "query method this tool wraps takes no as_of parameter "
                    "(matches the equivalent GraphQL surface, which exposes "
                    "no asOf argument here either)"
                ),
                "path": "$.asOf",
            }
        return None

    def _resolve_aggregation_field(
        anchor: EntityCapability, field: str, *, capability: str
    ) -> Optional[dict[str, Any]]:
        """Check `field` exists on `anchor` and has the requested boolean
        capability (`aggregatable` for facet_query_spec, `range_queryable`
        for field_range_query_spec) set on mosaic://capabilities. Returns
        None when the field is usable, else a coded error dict.

        Codes are copied verbatim from `graphql/resolvers.py`'s
        `_resolve_aggregate_field` (UNKNOWN_AGGREGATION_FIELD,
        UNAGGREGATABLE_FIELD) so a client sees the identical failure for
        the identical field over either transport -- the manifest already
        computed both flags (schema_typing.py), so there is no re-deriving
        GraphQL's own kind/multivalued/base-range logic here, only reading
        what it already decided."""
        fc = anchor.fields_by_name.get(field)
        if fc is None:
            aggregatable_names = sorted(
                n for n, f in anchor.fields_by_name.items() if getattr(f, capability)
            )
            return {
                "code": "UNKNOWN_AGGREGATION_FIELD",
                "message": (
                    f"unknown aggregation field {field!r} for {anchor.class_name!r}. "
                    f"Aggregatable fields: {aggregatable_names}"
                ),
                "path": "$.field",
            }
        if not getattr(fc, capability):
            noun = "faceted" if capability == "aggregatable" else "range-queried"
            return {
                "code": "UNAGGREGATABLE_FIELD",
                "message": (
                    f"{anchor.class_name}.{field} cannot be {noun} -- check "
                    f"mosaic://capabilities' {capability!r} flag before choosing a field"
                ),
                "path": "$.field",
            }
        return None

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

    @mcp.tool(
        annotations=ToolAnnotations(read_only_hint=True),
        description=(
            "Count entities matching a QuerySpec's criteria without "
            "materializing them (issue #195) -- a COUNT(*) under the exact "
            "predicate execute_query_spec's rows would match, so it always "
            "equals that call's 'total'. Use this for a 'how many' question "
            "instead of calling execute_query_spec and counting items -- "
            "cheaper, and correct even past execute_query_spec's page size. "
            "'sort' is rejected (no meaning for a scalar count)."
        ),
    )
    def count_query_spec(query_spec: dict, ctx: Context) -> dict[str, Any]:
        client = _client_from_context(ctx, hippo_client)
        manifest = _manifest_for(client)
        try:
            spec = parse_query_spec(query_spec)
        except QuerySpecShapeError as exc:
            return {"valid": False, "errors": [_shape_error_dict(exc)], "count": None}
        unsupported = _reject_unsupported_for_aggregate(spec, allow_as_of=True)
        if unsupported:
            return {"valid": False, "errors": [unsupported], "count": None}
        result = _validate_query_spec(spec, manifest)
        if not result.valid:
            return {"valid": False, "errors": [_error_dict(e) for e in result.errors], "count": None}
        compiled = compile_query_spec(spec, manifest)
        try:
            count = client.count(
                entity_type=compiled.entity_type, where=compiled.where, as_of=compiled.as_of
            )
        except MosaicValidationError as exc:
            return {
                "valid": False,
                "errors": [{"code": "COMPILE_ERROR", "message": str(exc), "path": "$"}],
                "count": None,
            }
        return {"valid": True, "errors": [], "count": count}

    @mcp.tool(
        annotations=ToolAnnotations(read_only_hint=True),
        description=(
            "Per-value counts of one field, under a QuerySpec's criteria "
            "(issue #195) -- e.g. how many Donor entities per cohort value. "
            "'field' must be aggregatable per mosaic://capabilities (a "
            "reference, multivalued, or structured field is not); an "
            "unaggregatable or unknown field is a coded error, not an empty "
            "result. Entities with no stored value for 'field' are not "
            "counted -- query absence separately with an is_null criterion. "
            "'sort' and 'asOf' are rejected (no meaning for a facet result; "
            "this mirrors GraphQL's facetCounts, which takes neither)."
        ),
    )
    def facet_query_spec(query_spec: dict, field: str, ctx: Context) -> dict[str, Any]:
        client = _client_from_context(ctx, hippo_client)
        manifest = _manifest_for(client)
        try:
            spec = parse_query_spec(query_spec)
        except QuerySpecShapeError as exc:
            return {"valid": False, "errors": [_shape_error_dict(exc)], "facets": None}
        unsupported = _reject_unsupported_for_aggregate(spec, allow_as_of=False)
        if unsupported:
            return {"valid": False, "errors": [unsupported], "facets": None}
        result = _validate_query_spec(spec, manifest)
        if not result.valid:
            return {"valid": False, "errors": [_error_dict(e) for e in result.errors], "facets": None}
        field_error = _resolve_aggregation_field(manifest[spec.anchor], field, capability="aggregatable")
        if field_error:
            return {"valid": False, "errors": [field_error], "facets": None}
        compiled = compile_query_spec(spec, manifest)
        try:
            buckets = client.facet_counts(compiled.entity_type, field, where=compiled.where)
        except MosaicValidationError as exc:
            return {
                "valid": False,
                "errors": [{"code": "COMPILE_ERROR", "message": str(exc), "path": "$"}],
                "facets": None,
            }
        return {
            "valid": True,
            "errors": [],
            "facets": [{"value": value, "count": count} for value, count in buckets],
        }

    @mcp.tool(
        annotations=ToolAnnotations(read_only_hint=True),
        description=(
            "Min/max of one field, under a QuerySpec's criteria (issue "
            "#195). 'field' must be range-queryable per mosaic://"
            "capabilities (numeric/date/datetime/time fields only -- an "
            "unaggregatable field is a coded error, not an empty result). "
            "Returns {min: null, max: null} (a VALID result, check 'valid' "
            "not 'min') when no matching entity has a stored value. 'sort' "
            "and 'asOf' are rejected (no meaning for a range result; this "
            "mirrors GraphQL's fieldRange, which takes neither)."
        ),
    )
    def field_range_query_spec(query_spec: dict, field: str, ctx: Context) -> dict[str, Any]:
        client = _client_from_context(ctx, hippo_client)
        manifest = _manifest_for(client)
        try:
            spec = parse_query_spec(query_spec)
        except QuerySpecShapeError as exc:
            return {"valid": False, "errors": [_shape_error_dict(exc)], "min": None, "max": None}
        unsupported = _reject_unsupported_for_aggregate(spec, allow_as_of=False)
        if unsupported:
            return {"valid": False, "errors": [unsupported], "min": None, "max": None}
        result = _validate_query_spec(spec, manifest)
        if not result.valid:
            return {
                "valid": False,
                "errors": [_error_dict(e) for e in result.errors],
                "min": None,
                "max": None,
            }
        field_error = _resolve_aggregation_field(manifest[spec.anchor], field, capability="range_queryable")
        if field_error:
            return {"valid": False, "errors": [field_error], "min": None, "max": None}
        compiled = compile_query_spec(spec, manifest)
        try:
            lo, hi = client.field_range(compiled.entity_type, field, where=compiled.where)
        except MosaicValidationError as exc:
            return {
                "valid": False,
                "errors": [{"code": "COMPILE_ERROR", "message": str(exc), "path": "$"}],
                "min": None,
                "max": None,
            }
        return {"valid": True, "errors": [], "min": lo, "max": hi}

    @mcp.tool(
        annotations=ToolAnnotations(read_only_hint=True),
        description=(
            "Full-text search over one entity type, composed with a "
            "QuerySpec's criteria (issue #196) -- e.g. donors whose notes "
            "mention a term, further filtered by cohort. Returns the same "
            "envelope as execute_query_spec ({valid, errors, items, "
            "total}). Results come back in FTS rank order; an explicit "
            "'sort' overrides rank. Check mosaic://capabilities' "
            "'search_available'/'searchable' flags before calling -- an "
            "entity or field with no searchable slot returns an empty "
            "result, not an error (matches GraphQL's own searchDonors "
            "etc., which has the same silent-empty behavior by design)."
        ),
    )
    def search_query_spec(
        query_spec: dict, q: str, ctx: Context, limit: int = 100, offset: int = 0
    ) -> dict[str, Any]:
        client = _client_from_context(ctx, hippo_client)
        manifest = _manifest_for(client)
        if not (1 <= limit <= MAX_EXECUTE_LIMIT):
            return {
                "valid": False,
                "errors": [{
                    "code": "INVALID_LIMIT",
                    "message": f"'limit' must be between 1 and {MAX_EXECUTE_LIMIT} "
                    f"(matches execute_query_spec's bound), got {limit}",
                    "path": "$.limit",
                }],
                "items": None,
                "total": None,
            }
        if offset < 0:
            return {
                "valid": False,
                "errors": [{"code": "INVALID_OFFSET", "message": "'offset' must be >= 0", "path": "$.offset"}],
                "items": None,
                "total": None,
            }
        try:
            spec = parse_query_spec(query_spec)
        except QuerySpecShapeError as exc:
            return {"valid": False, "errors": [_shape_error_dict(exc)], "items": None, "total": None}
        unsupported = _reject_unsupported_for_aggregate(spec, allow_sort=True, allow_as_of=False)
        if unsupported:
            return {"valid": False, "errors": [unsupported], "items": None, "total": None}
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
            page = client.search(
                entity_type=compiled.entity_type,
                query=q,
                limit=limit,
                offset=offset,
                where=compiled.where,
                order_by=compiled.order_by,
                order_dir=compiled.order_dir,
            )
        except MosaicValidationError as exc:
            return {
                "valid": False,
                "errors": [{"code": "COMPILE_ERROR", "message": str(exc), "path": "$"}],
                "items": None,
                "total": None,
            }
        dumped = page.model_dump(mode="json")
        return {"valid": True, "errors": [], "items": dumped["items"], "total": dumped["total"]}

    exon_url = os.environ.get(EXON_URL_ENV, "").strip()
    if exon_url:

        @mcp.tool(
            annotations=ToolAnnotations(read_only_hint=True),
            description=(
                "Build a QuerySpec conversationally, one turn at a time "
                "(issue #186): send the user's new utterance plus the "
                "conversation so far, get back a single turn. A turn is "
                "either a 'proposal' (an updated, Mosaic-validated "
                "QuerySpec plus a plain-language restatement of what it "
                "now means) or a 'clarification' (a question back, no "
                "spec change), or 'error' if the planning service is "
                "unreachable or returned something invalid. Pass "
                "'edit_turn_id' to redo an EARLIER turn with a new "
                "utterance -- turns after it are recomputed, and any that "
                "no longer make sense come back in 'suspended_turn_ids' "
                "for the user to re-prompt rather than being silently "
                "dropped. Stateless: you own the turn list and must pass "
                "it back each call; nothing is persisted here. ALWAYS "
                "replace your turn list with the returned 'turns' -- it is "
                "the authoritative conversation after the call, and after "
                "an edit the recomputed later turns are only available "
                "there. If 'turns' is absent (an error turn), nothing was "
                "applied and your existing list is still current. This "
                "never executes anything -- hand a returned proposal to "
                "execute_query_spec only on an explicit user action."
            ),
        )
        def converse_query_spec(
            utterance: str,
            ctx: Context,
            query_spec: Optional[dict] = None,
            turns: Optional[list[dict]] = None,
            edit_turn_id: Optional[str] = None,
        ) -> dict[str, Any]:
            client = _client_from_context(ctx, hippo_client)
            manifest = _manifest_for(client)
            payload = {
                "utterance": utterance,
                "query_spec": query_spec,
                "turns": turns or [],
                "edit_turn_id": edit_turn_id,
            }

            # Import here, not at module scope: httpx2 arrives with the
            # `mcp` extra (the MCP SDK's own HTTP dependency), so it is
            # guaranteed wherever this module can be imported at all --
            # but keeping it local means the rest of the server has no
            # import-time coupling to an HTTP client it never uses.
            import httpx2

            try:
                with httpx2.Client(timeout=_exon_timeout()) as http:
                    response = http.post(exon_url, json=payload)
                    response.raise_for_status()
                    body = response.json()
            except httpx2.TimeoutException:
                return {
                    "turn": _error_turn(
                        utterance,
                        f"The conversational planning service at {exon_url} did not "
                        f"respond within {_exon_timeout():g}s. The conversation is "
                        f"unchanged -- retrying the same utterance is safe.",
                    ),
                    "suspended_turn_ids": [],
                }
            except httpx2.HTTPStatusError as exc:
                # Exon's own 4xx (e.g. an edit_turn_id it doesn't know, or
                # a query_spec disagreeing with its turn-derived state)
                # is a caller-contract problem worth surfacing verbatim --
                # it names what disagreed, which is actionable.
                detail = (exc.response.text or "").strip()[:500]
                return {
                    "turn": _error_turn(
                        utterance,
                        f"The conversational planning service at {exon_url} rejected "
                        f"the request. {detail or 'No detail provided.'}",
                    ),
                    "suspended_turn_ids": [],
                }
            except (httpx2.HTTPError, ValueError) as exc:
                # ValueError covers a 2xx body that isn't JSON at all.
                return {
                    "turn": _error_turn(
                        utterance,
                        f"Could not reach the conversational planning service at "
                        f"{exon_url}: {exc}",
                    ),
                    "suspended_turn_ids": [],
                }

            malformed = _reject_malformed_exon_response(body)
            if malformed:
                return {
                    "turn": _error_turn(utterance, malformed),
                    "suspended_turn_ids": [],
                }

            turn = body["turn"]
            suspended = body.get("suspended_turn_ids") or []
            turns = body.get("turns") or []

            # Re-validate IN-PROCESS (a direct function call, never back
            # through MCP -- same process already hosts the validator, and
            # a self-call would be a needless cycle). Only a `proposal`
            # carries a spec; `clarification`/`suspended` turns have none
            # by contract, already checked above.
            #
            # EVERY proposal is checked, not just `turn`. After an edit, the
            # planning service recomputes the turns following the edited one,
            # so `turns` can carry freshly-generated specs this deployment
            # has never seen -- validating only `turn` would let those reach
            # the caller unchecked, which is exactly the guarantee this
            # re-validation exists to hold.
            for candidate in [turn, *turns]:
                if candidate.get("status") != "proposal":
                    continue
                which = (
                    "proposed" if candidate is turn
                    else f"recomputed (turn id {candidate.get('id')!r})"
                )
                try:
                    spec = parse_query_spec(candidate["query_spec"])
                except QuerySpecShapeError as exc:
                    return {
                        "turn": _error_turn(
                            utterance,
                            f"The planning service {which} a QuerySpec that is not "
                            f"well-formed ({exc.code} at {exc.path}: {exc}). Nothing "
                            f"was applied.",
                        ),
                        "suspended_turn_ids": [],
                    }
                result = _validate_query_spec(spec, manifest)
                if not result.valid:
                    codes = "; ".join(f"{e.code} at {e.path}: {e.message}" for e in result.errors)
                    return {
                        "turn": _error_turn(
                            utterance,
                            f"The planning service {which} a QuerySpec that failed "
                            f"validation against this deployment's capabilities: "
                            f"{codes}. Nothing was applied.",
                        ),
                        "suspended_turn_ids": [],
                    }

            return {
                "turn": turn,
                "suspended_turn_ids": list(suspended),
                "turns": list(turns),
            }

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

9. A QuerySpec has NO aggregation shape of its own -- execute_query_spec \
always returns full entity rows, never a count or a per-value breakdown. \
If the question is "how many", "how many X per Y", or "what's the \
min/max of X", do NOT answer it by listing rows (sorted or not) and do \
NOT count/group them yourself -- call count_query_spec / \
facet_query_spec / field_range_query_spec instead. A row list is not an \
answer to a counting question, even when every row in it is correct.

10. For a free-text/keyword question ("mentions", "contains the word", \
"about X"), prefer search_query_spec over a `contains` FieldCondition -- \
`contains` is a substring match on ONE field you name; search_query_spec \
ranks across every searchable slot on the entity at once. Check \
search_available on mosaic://capabilities first: an entity with no \
searchable slot returns an empty result, not an error.

Workflow: call validate_query_spec first if you want to check a draft \
without running it; call execute_query_spec once you're ready to fetch \
results -- it validates internally too, and returns the exact same \
{valid, errors} shape (plus items/total) if something's still wrong, so \
you can read the error, fix the one thing it names, and retry."""


def _mosaic_version() -> str:
    from mosaic import __version__

    return __version__
