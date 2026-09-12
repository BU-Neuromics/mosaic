"""Tests for the ``converseQuerySpec`` GraphQL mutation (issue #205): the
GraphQL transport surface for the in-process ``converse_query_spec``
handler already exercised by ``tests/mcp/test_mcp_converse_tool.py``.

This mutation is a THIN wrapper: ``mosaic.core.converse_query_spec.
run_converse_turn`` (shared verbatim with the MCP tool) owns the planning
delegation, the ADR-0010 relay terms, and the in-process re-validation --
none of that is re-tested here. What IS specific to this transport and
worth covering:

(a) the mutation is absent entirely when ``MOSAIC_EXON_URL`` is unset
    (mirrors the MCP tool's own registration gate),
(b) a happy-path proposal round-trips through the GraphQL types, and
(c) the deliberate GraphQL-side design decision (issue #205): on a
    rejected/error turn, ``turns`` is ALWAYS a non-empty list (the
    caller's own prior turns, unchanged) -- never ``[]`` and never
    absent, unlike the underlying handler's own envelope.

Exon itself is stubbed at the HTTP boundary (``httpx2.Client``), exactly
like the MCP tests -- the wire contract is what is under test.
"""

from __future__ import annotations

from mosaic.core.converse_query_spec import EXON_URL_ENV
from mosaic.graphql.resolvers import build_graphql_schema
from mosaic.graphql.schema_builder import GraphQLTypeBuilder

VALID_SPEC = {"v": 1, "anchor": "Donor", "mode": "AND", "criteria": []}

CONVERSE_MUTATION = """
mutation Converse(
    $utterance: String!
    $querySpec: JSON
    $turns: [ConversationTurnInput!]
    $editTurnId: ID
) {
  converseQuerySpec(
    utterance: $utterance
    querySpec: $querySpec
    turns: $turns
    editTurnId: $editTurnId
  ) {
    turn { id utterance status message querySpec }
    turns { id utterance status message querySpec }
    suspendedTurnIds
  }
}
"""


class _StubResponse:
    def __init__(self, payload, *, status=200, text=""):
        self._payload = payload
        self._status = status
        self.status_code = status
        self.text = text

    def raise_for_status(self):
        if self._status >= 400:
            import httpx2

            raise httpx2.HTTPStatusError(f"{self._status}", request=None, response=self)

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _StubClient:
    calls: list = []

    def __init__(self, response=None, raise_exc=None, **kwargs):
        self._response = response
        self._raise = raise_exc

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, json=None):
        type(self).calls.append({"url": url, "json": json})
        if self._raise is not None:
            raise self._raise
        return self._response


def _install_stub(monkeypatch, *, response=None, raise_exc=None):
    import httpx2

    _StubClient.calls = []

    def factory(**kwargs):
        return _StubClient(response=response, raise_exc=raise_exc, **kwargs)

    monkeypatch.setattr(httpx2, "Client", factory)
    return _StubClient


def _build_schema(registry):
    """Build a fresh GraphQL schema -- callers must set/unset
    MOSAIC_EXON_URL via monkeypatch BEFORE calling this, since the
    mutation's presence is decided at schema-build time."""
    builder = GraphQLTypeBuilder(registry).build()
    return build_graphql_schema(registry, builder=builder), builder


def _execute(schema, builder, hippo_client, query, variables=None):
    result = schema.execute_sync(
        query,
        variable_values=variables or {},
        context_value={"client": hippo_client, "builder": builder},
    )
    return result


def _mutation_field_names(schema, builder, hippo_client) -> set[str]:
    result = _execute(
        schema,
        builder,
        hippo_client,
        "{ __type(name: \"Mutation\") { fields { name } } }",
    )
    assert result.errors is None, result.errors
    return {f["name"] for f in result.data["__type"]["fields"]}


class TestRegistrationGating:
    """Decision 8 / issue #186's gate, mirrored on this transport: the
    mutation must be entirely absent from the schema when unconfigured --
    an unconfigured deployment must not advertise what it cannot serve."""

    def test_absent_when_env_unset(self, registry, hippo_client, monkeypatch):
        monkeypatch.delenv(EXON_URL_ENV, raising=False)
        schema, builder = _build_schema(registry)
        names = _mutation_field_names(schema, builder, hippo_client)
        assert "converseQuerySpec" not in names
        # The rest of the mutation surface is unaffected.
        assert "ingestBatch" in names

    def test_absent_when_env_blank(self, registry, hippo_client, monkeypatch):
        monkeypatch.setenv(EXON_URL_ENV, "   ")
        schema, builder = _build_schema(registry)
        assert "converseQuerySpec" not in _mutation_field_names(schema, builder, hippo_client)

    def test_present_when_configured(self, registry, hippo_client, monkeypatch):
        monkeypatch.setenv(EXON_URL_ENV, "http://exon.internal:9100/turn")
        schema, builder = _build_schema(registry)
        assert "converseQuerySpec" in _mutation_field_names(schema, builder, hippo_client)

    def test_calling_it_when_absent_is_a_validation_error(
        self, registry, hippo_client, monkeypatch
    ):
        monkeypatch.delenv(EXON_URL_ENV, raising=False)
        schema, builder = _build_schema(registry)
        result = _execute(
            schema, builder, hippo_client, CONVERSE_MUTATION, {"utterance": "donors"}
        )
        assert result.errors is not None
        assert any("converseQuerySpec" in str(e) for e in result.errors)


class TestHappyPath:
    def test_proposal_round_trips(self, registry, hippo_client, monkeypatch):
        monkeypatch.setenv(EXON_URL_ENV, "http://exon.internal:9100/turn")
        _install_stub(
            monkeypatch,
            response=_StubResponse(
                {
                    "turn": {
                        "id": "t1",
                        "utterance": "female donors",
                        "status": "proposal",
                        "query_spec": {
                            "v": 1,
                            "anchor": "Donor",
                            "mode": "AND",
                            "criteria": [
                                {"kind": "field", "slot": "sex", "op": "eq", "value": "female"}
                            ],
                        },
                        "message": "Filtering to female donors.",
                    },
                    "suspended_turn_ids": [],
                }
            ),
        )
        schema, builder = _build_schema(registry)
        result = _execute(
            schema,
            builder,
            hippo_client,
            CONVERSE_MUTATION,
            {"utterance": "female donors"},
        )
        assert result.errors is None, result.errors
        payload = result.data["converseQuerySpec"]
        assert payload["turn"]["status"] == "proposal"
        assert payload["turn"]["id"] == "t1"
        assert payload["turn"]["querySpec"]["anchor"] == "Donor"
        assert payload["suspendedTurnIds"] == []
        # No `turns` from Exon here -- back-compat success path -- so the
        # mutation fills it in from the (empty) input turns.
        assert payload["turns"] == []

    def test_edit_turn_id_and_recomputed_turns_pass_through(
        self, registry, hippo_client, monkeypatch
    ):
        monkeypatch.setenv(EXON_URL_ENV, "http://exon.internal:9100/turn")
        convo = [
            {
                "id": "t1",
                "utterance": "cerebellum samples instead",
                "status": "proposal",
                "query_spec": VALID_SPEC,
                "message": "Cerebellum samples.",
            },
            {
                "id": "t2",
                "utterance": "only from female donors",
                "status": "proposal",
                "query_spec": VALID_SPEC,
                "message": "Cerebellum samples from female donors.",
            },
        ]
        stub = _install_stub(
            monkeypatch,
            response=_StubResponse(
                {"turn": convo[0], "suspended_turn_ids": ["t3"], "turns": convo}
            ),
        )
        schema, builder = _build_schema(registry)
        result = _execute(
            schema,
            builder,
            hippo_client,
            CONVERSE_MUTATION,
            {
                "utterance": "cerebellum samples instead",
                "editTurnId": "t1",
            },
        )
        assert result.errors is None, result.errors
        payload = result.data["converseQuerySpec"]
        assert [t["id"] for t in payload["turns"]] == ["t1", "t2"]
        assert payload["turns"][1]["message"] == "Cerebellum samples from female donors."
        assert payload["suspendedTurnIds"] == ["t3"]
        assert stub.calls[0]["json"]["edit_turn_id"] == "t1"

    def test_prior_turns_argument_reaches_exon(self, registry, hippo_client, monkeypatch):
        monkeypatch.setenv(EXON_URL_ENV, "http://exon.internal:9100/turn")
        # As a GraphQL variable (input type field is `querySpec`, camelCase)...
        prior = {
            "id": "t1",
            "utterance": "show me donors",
            "status": "proposal",
            "querySpec": VALID_SPEC,
            "message": "All donors.",
        }
        # ...but the wire payload sent to Exon is the snake_case shape
        # Decision 8 actually specifies -- GraphQL's own naming convention
        # is a transport-local concern that must not leak onto the wire.
        prior_wire = {
            "id": "t1",
            "utterance": "show me donors",
            "status": "proposal",
            "query_spec": VALID_SPEC,
            "message": "All donors.",
        }
        stub = _install_stub(
            monkeypatch,
            response=_StubResponse(
                {
                    "turn": {
                        "id": "t2",
                        "utterance": "only female",
                        "status": "proposal",
                        "query_spec": VALID_SPEC,
                        "message": "Female donors.",
                    },
                    "suspended_turn_ids": [],
                }
            ),
        )
        schema, builder = _build_schema(registry)
        result = _execute(
            schema,
            builder,
            hippo_client,
            CONVERSE_MUTATION,
            {"utterance": "only female", "turns": [prior]},
        )
        assert result.errors is None, result.errors
        assert stub.calls[0]["json"]["turns"] == [prior_wire]


class TestRejectionPathAlwaysReturnsTurns:
    """The deliberate design decision from issue #205: unlike the
    underlying handler (which OMITS `turns` on every failure path, per
    #200), converseQuerySpec's `turns` is non-null, so a failure must
    still return something -- specifically the caller's own prior turns,
    unchanged, never `[]` and never absent."""

    def test_rejected_proposal_echoes_prior_turns_unchanged(
        self, registry, hippo_client, monkeypatch
    ):
        monkeypatch.setenv(EXON_URL_ENV, "http://exon.internal:9100/turn")
        prior = {
            "id": "t1",
            "utterance": "show me donors",
            "status": "proposal",
            "querySpec": VALID_SPEC,
            "message": "All donors.",
        }
        # Exon proposes a QuerySpec with an unknown slot -- Mosaic must
        # reject it in-process rather than hand back a bad proposal.
        _install_stub(
            monkeypatch,
            response=_StubResponse(
                {
                    "turn": {
                        "id": "t2",
                        "utterance": "by eye colour",
                        "status": "proposal",
                        "query_spec": {
                            "v": 1,
                            "anchor": "Donor",
                            "mode": "AND",
                            "criteria": [
                                {
                                    "kind": "field",
                                    "slot": "eye_colour",
                                    "op": "eq",
                                    "value": "blue",
                                }
                            ],
                        },
                        "message": "Filtering by eye colour.",
                    },
                    "suspended_turn_ids": [],
                }
            ),
        )
        schema, builder = _build_schema(registry)
        result = _execute(
            schema,
            builder,
            hippo_client,
            CONVERSE_MUTATION,
            {"utterance": "by eye colour", "turns": [prior]},
        )
        assert result.errors is None, result.errors
        payload = result.data["converseQuerySpec"]
        assert payload["turn"]["status"] == "error"
        assert payload["turn"]["id"] is None
        assert "UNKNOWN_SLOT" in payload["turn"]["message"]
        # The load-bearing assertion: `turns` is NOT empty and NOT absent
        # -- it is exactly the caller's own prior turns, unchanged.
        assert payload["turns"] == [
            {
                "id": "t1",
                "utterance": "show me donors",
                "status": "proposal",
                "message": "All donors.",
                "querySpec": VALID_SPEC,
            }
        ]

    def test_transport_failure_echoes_prior_turns_unchanged(
        self, registry, hippo_client, monkeypatch
    ):
        import httpx2

        monkeypatch.setenv(EXON_URL_ENV, "http://exon.internal:9100/turn")
        prior = {
            "id": "t1",
            "utterance": "show me donors",
            "status": "proposal",
            "querySpec": VALID_SPEC,
            "message": "All donors.",
        }
        _install_stub(monkeypatch, raise_exc=httpx2.TimeoutException("timed out"))
        schema, builder = _build_schema(registry)
        result = _execute(
            schema,
            builder,
            hippo_client,
            CONVERSE_MUTATION,
            {"utterance": "donors again", "turns": [prior]},
        )
        assert result.errors is None, result.errors
        payload = result.data["converseQuerySpec"]
        assert payload["turn"]["status"] == "error"
        assert "did not respond" in payload["turn"]["message"]
        assert payload["turns"] == [
            {
                "id": "t1",
                "utterance": "show me donors",
                "status": "proposal",
                "message": "All donors.",
                "querySpec": VALID_SPEC,
            }
        ]

    def test_rejection_with_no_prior_turns_is_still_a_list_not_null(
        self, registry, hippo_client, monkeypatch
    ):
        """When there WERE no prior turns, echoing them back is correctly
        `[]` -- the invariant is 'never absent', not 'never empty'."""
        import httpx2

        monkeypatch.setenv(EXON_URL_ENV, "http://exon.internal:9100/turn")
        _install_stub(monkeypatch, raise_exc=httpx2.TimeoutException("timed out"))
        schema, builder = _build_schema(registry)
        result = _execute(
            schema, builder, hippo_client, CONVERSE_MUTATION, {"utterance": "donors"}
        )
        assert result.errors is None, result.errors
        payload = result.data["converseQuerySpec"]
        assert payload["turn"]["status"] == "error"
        assert payload["turns"] == []
