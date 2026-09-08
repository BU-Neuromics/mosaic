"""Tests for ``converse_query_spec`` (issue #186): the MCP boundary's
conversational turn-taking delegate.

Unlike every other tool on this surface, this one wraps no
``MosaicClient`` method — it delegates over HTTP to Exon's planning core.
So the ground truth here is different in kind: what matters is that Mosaic
(a) only advertises the tool when it is configured to serve it, (b) passes
Decision 8's request shape through faithfully, (c) NEVER hands back a
``proposal`` whose ``QuerySpec`` this deployment's own validator rejects,
and (d) turns every transport-level failure into an ``error`` turn inside
the same envelope rather than an MCP exception.

Exon itself is stubbed at the HTTP boundary (``httpx2.Client``), not
mocked at a Python-function seam: the wire contract is the thing under
test, so the test drives the same JSON a real Exon would return. No
network, no model calls, no Exon checkout required.
"""

from __future__ import annotations

import json

import pytest
from mcp.client.client import Client

from mosaic.mcp.server import EXON_ROLE_NAME, EXON_URL_ENV, create_mcp_server

EXON_URL = "http://exon.internal:9100/turn"

VALID_SPEC = {"v": 1, "anchor": "Donor", "mode": "AND", "criteria": []}


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def exon_configured(monkeypatch):
    monkeypatch.setenv(EXON_URL_ENV, EXON_URL)


class _StubResponse:
    def __init__(self, payload, *, status=200, text=""):
        self._payload = payload
        self._status = status
        # A real httpx2 response exposes status_code; the tool reads it to
        # classify a 4xx for the client without echoing the body.
        self.status_code = status
        self.text = text

    def raise_for_status(self):
        if self._status >= 400:
            import httpx2

            raise httpx2.HTTPStatusError(
                f"{self._status}", request=None, response=self
            )

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _StubClient:
    """Stands in for ``httpx2.Client`` as a context manager, recording the
    request so a test can assert on the exact wire payload."""

    calls: list = []
    inits: list = []

    def __init__(self, response=None, raise_exc=None, **kwargs):
        self._response = response
        self._raise = raise_exc
        self.init_kwargs = kwargs
        type(self).inits.append(kwargs)

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
    _StubClient.inits = []

    def factory(**kwargs):
        return _StubClient(response=response, raise_exc=raise_exc, **kwargs)

    monkeypatch.setattr(httpx2, "Client", factory)
    return _StubClient


async def _call_tool(server, name: str, args: dict) -> dict:
    async with Client(server) as client:
        result = await client.call_tool(name, args)
        (content,) = result.content
        return json.loads(content.text)


async def _tool_names(server) -> set[str]:
    async with Client(server) as client:
        return {t.name for t in (await client.list_tools()).tools}


@pytest.mark.anyio
class TestRegistrationGating:
    """Decision 8: the tool is absent entirely when unconfigured — an
    unconfigured deployment must not advertise what it cannot serve."""

    async def test_absent_when_env_unset(self, hippo_client, monkeypatch):
        monkeypatch.delenv(EXON_URL_ENV, raising=False)
        names = await _tool_names(create_mcp_server(hippo_client))
        assert "converse_query_spec" not in names
        # The rest of the surface is unaffected.
        assert "validate_query_spec" in names
        assert "execute_query_spec" in names

    async def test_absent_when_env_blank(self, hippo_client, monkeypatch):
        monkeypatch.setenv(EXON_URL_ENV, "   ")
        assert "converse_query_spec" not in await _tool_names(create_mcp_server(hippo_client))

    async def test_present_when_configured(self, hippo_client, exon_configured):
        assert "converse_query_spec" in await _tool_names(create_mcp_server(hippo_client))

    async def test_instructions_mention_it_only_when_configured(
        self, hippo_client, monkeypatch
    ):
        monkeypatch.delenv(EXON_URL_ENV, raising=False)
        assert "converse_query_spec" not in (create_mcp_server(hippo_client).instructions or "")
        monkeypatch.setenv(EXON_URL_ENV, EXON_URL)
        assert "converse_query_spec" in (create_mcp_server(hippo_client).instructions or "")


@pytest.mark.anyio
class TestRequestShape:
    async def test_sends_decision_8_request_shape(
        self, hippo_client, exon_configured, monkeypatch
    ):
        stub = _install_stub(
            monkeypatch,
            response=_StubResponse(
                {
                    "turn": {
                        "id": "t2",
                        "utterance": "only female donors",
                        "status": "proposal",
                        "query_spec": VALID_SPEC,
                        "message": "Filtering to female donors.",
                    },
                    "suspended_turn_ids": [],
                }
            ),
        )
        prior = [
            {
                "id": "t1",
                "utterance": "show me donors",
                "status": "proposal",
                "query_spec": VALID_SPEC,
                "message": "All donors.",
            }
        ]
        await _call_tool(
            create_mcp_server(hippo_client),
            "converse_query_spec",
            {
                "utterance": "only female donors",
                "query_spec": VALID_SPEC,
                "turns": prior,
                "edit_turn_id": None,
            },
        )
        (call,) = stub.calls
        assert call["url"] == EXON_URL
        assert call["json"] == {
            "utterance": "only female donors",
            "query_spec": VALID_SPEC,
            "turns": prior,
            "edit_turn_id": None,
        }

    async def test_omitted_optionals_become_contract_defaults(
        self, hippo_client, exon_configured, monkeypatch
    ):
        # turns defaults to [], not None: Exon's contract takes a list.
        stub = _install_stub(
            monkeypatch,
            response=_StubResponse(
                {
                    "turn": {
                        "id": "t1",
                        "utterance": "show me donors",
                        "status": "clarification",
                        "query_spec": None,
                        "message": "Which cohort?",
                    }
                }
            ),
        )
        await _call_tool(
            create_mcp_server(hippo_client),
            "converse_query_spec",
            {"utterance": "show me donors"},
        )
        (call,) = stub.calls
        assert call["json"] == {
            "utterance": "show me donors",
            "query_spec": None,
            "turns": [],
            "edit_turn_id": None,
        }

    async def test_edit_turn_id_passes_through(
        self, hippo_client, exon_configured, monkeypatch
    ):
        stub = _install_stub(
            monkeypatch,
            response=_StubResponse(
                {
                    "turn": {
                        "id": "t1",
                        "utterance": "samples instead",
                        "status": "proposal",
                        "query_spec": VALID_SPEC,
                        "message": "Switched anchor.",
                    },
                    "suspended_turn_ids": ["t2", "t3"],
                }
            ),
        )
        payload = await _call_tool(
            create_mcp_server(hippo_client),
            "converse_query_spec",
            {"utterance": "samples instead", "edit_turn_id": "t1"},
        )
        assert stub.calls[0]["json"]["edit_turn_id"] == "t1"
        # Suspended ids are surfaced, never swallowed.
        assert payload["suspended_turn_ids"] == ["t2", "t3"]


@pytest.mark.anyio
class TestReValidation:
    """The load-bearing guarantee: Mosaic re-validates Exon's QuerySpec
    in-process before ever returning a proposal, so a stale or bypassed
    Exon-side check cannot put an invalid spec in front of Aperture."""

    async def test_valid_proposal_passes_through(
        self, hippo_client, exon_configured, monkeypatch
    ):
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
        payload = await _call_tool(
            create_mcp_server(hippo_client),
            "converse_query_spec",
            {"utterance": "female donors"},
        )
        assert payload["turn"]["status"] == "proposal"
        assert payload["turn"]["query_spec"]["anchor"] == "Donor"

    async def test_unknown_slot_becomes_error_turn_not_proposal(
        self, hippo_client, exon_configured, monkeypatch
    ):
        _install_stub(
            monkeypatch,
            response=_StubResponse(
                {
                    "turn": {
                        "id": "t1",
                        "utterance": "donors by eye colour",
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
        payload = await _call_tool(
            create_mcp_server(hippo_client),
            "converse_query_spec",
            {"utterance": "donors by eye colour"},
        )
        # Exon called it a proposal; Mosaic must not.
        assert payload["turn"]["status"] == "error"
        assert payload["turn"]["query_spec"] is None
        assert "UNKNOWN_SLOT" in payload["turn"]["message"]

    async def test_unknown_anchor_becomes_error_turn(
        self, hippo_client, exon_configured, monkeypatch
    ):
        _install_stub(
            monkeypatch,
            response=_StubResponse(
                {
                    "turn": {
                        "id": "t1",
                        "utterance": "show me spaceships",
                        "status": "proposal",
                        "query_spec": {
                            "v": 1,
                            "anchor": "Spaceship",
                            "mode": "AND",
                            "criteria": [],
                        },
                        "message": "Filtering spaceships.",
                    }
                }
            ),
        )
        payload = await _call_tool(
            create_mcp_server(hippo_client),
            "converse_query_spec",
            {"utterance": "show me spaceships"},
        )
        assert payload["turn"]["status"] == "error"
        assert payload["turn"]["query_spec"] is None

    async def test_malformed_spec_shape_becomes_error_turn(
        self, hippo_client, exon_configured, monkeypatch
    ):
        _install_stub(
            monkeypatch,
            response=_StubResponse(
                {
                    "turn": {
                        "id": "t1",
                        "utterance": "donors",
                        "status": "proposal",
                        # Missing the required "v" discriminator.
                        "query_spec": {"anchor": "Donor", "mode": "AND", "criteria": []},
                        "message": "Donors.",
                    }
                }
            ),
        )
        payload = await _call_tool(
            create_mcp_server(hippo_client),
            "converse_query_spec",
            {"utterance": "donors"},
        )
        assert payload["turn"]["status"] == "error"
        assert "not well-formed" in payload["turn"]["message"]

    async def test_clarification_is_not_validated(
        self, hippo_client, exon_configured, monkeypatch
    ):
        # A clarification carries no spec, so there is nothing to validate
        # and it must pass through untouched.
        _install_stub(
            monkeypatch,
            response=_StubResponse(
                {
                    "turn": {
                        "id": "t1",
                        "utterance": "the recent ones",
                        "status": "clarification",
                        "query_spec": None,
                        "message": "Recent by collection date, or by ingest date?",
                    }
                }
            ),
        )
        payload = await _call_tool(
            create_mcp_server(hippo_client),
            "converse_query_spec",
            {"utterance": "the recent ones"},
        )
        assert payload["turn"]["status"] == "clarification"
        assert payload["turn"]["message"].startswith("Recent by")


@pytest.mark.anyio
class TestFailureSemantics:
    """Decision 8: every failure comes back as an 'error' turn inside the
    envelope Aperture already branches on — never a bare tool exception."""

    async def test_timeout_becomes_error_turn(
        self, hippo_client, exon_configured, monkeypatch
    ):
        import httpx2

        _install_stub(monkeypatch, raise_exc=httpx2.TimeoutException("timed out"))
        payload = await _call_tool(
            create_mcp_server(hippo_client),
            "converse_query_spec",
            {"utterance": "donors"},
        )
        assert payload["turn"]["status"] == "error"
        assert payload["turn"]["query_spec"] is None
        assert "did not respond" in payload["turn"]["message"]
        # Says the conversation is unchanged, so a client knows retrying is safe.
        assert "unchanged" in payload["turn"]["message"]
        # ADR-0010 decision 5: the role, never the address.
        assert EXON_URL not in payload["turn"]["message"]
        assert "exon.internal" not in payload["turn"]["message"]
        assert EXON_ROLE_NAME.lower() in payload["turn"]["message"].lower()

    async def test_unreachable_becomes_error_turn(
        self, hippo_client, exon_configured, monkeypatch
    ):
        import httpx2

        _install_stub(monkeypatch, raise_exc=httpx2.RequestError("connection refused"))
        payload = await _call_tool(
            create_mcp_server(hippo_client),
            "converse_query_spec",
            {"utterance": "donors"},
        )
        assert payload["turn"]["status"] == "error"
        assert "Could not reach" in payload["turn"]["message"]
        # ADR-0010 decision 5, and the exception text is the operator's,
        # not the caller's -- neither address nor cause on the turn.
        assert EXON_URL not in payload["turn"]["message"]
        assert "connection refused" not in payload["turn"]["message"]

    async def test_exon_4xx_reports_status_to_client_and_detail_to_the_log(
        self, hippo_client, exon_configured, monkeypatch, caplog
    ):
        # Exon's own 400 (e.g. Decision 9's query_spec/turns disagreement)
        # names what disagreed. That detail is actionable but it is the
        # planner's raw text, so ADR-0010 decision 5 splits it: the client
        # gets a Mosaic-authored classification (the status code), the
        # operator gets the body in the log.
        _install_stub(
            monkeypatch,
            response=_StubResponse(
                None,
                status=400,
                text="'query_spec' does not match the state derived from 'turns'",
            ),
        )
        with caplog.at_level("WARNING", logger="mosaic.mcp.server"):
            payload = await _call_tool(
                create_mcp_server(hippo_client),
                "converse_query_spec",
                {"utterance": "donors"},
            )
        assert payload["turn"]["status"] == "error"
        assert "rejected the request (HTTP 400)" in payload["turn"]["message"]
        # The upstream text is NOT on the turn ...
        assert "does not match the state derived" not in payload["turn"]["message"]
        # ... but it is not lost either.
        assert "does not match the state derived" in caplog.text
        assert EXON_URL in caplog.text

    async def test_non_json_body_becomes_error_turn(
        self, hippo_client, exon_configured, monkeypatch
    ):
        _install_stub(
            monkeypatch,
            response=_StubResponse(ValueError("not json")),
        )
        payload = await _call_tool(
            create_mcp_server(hippo_client),
            "converse_query_spec",
            {"utterance": "donors"},
        )
        assert payload["turn"]["status"] == "error"

    async def test_error_turn_has_no_id(
        self, hippo_client, exon_configured, monkeypatch
    ):
        # An error is not a rewindable conversational step.
        import httpx2

        _install_stub(monkeypatch, raise_exc=httpx2.TimeoutException("t"))
        payload = await _call_tool(
            create_mcp_server(hippo_client),
            "converse_query_spec",
            {"utterance": "donors"},
        )
        assert payload["turn"]["id"] is None


@pytest.mark.anyio
class TestOutOfContractResponses:
    """Mosaic is the only thing between an out-of-contract Exon and
    Aperture's UI, so an unrecognized shape fails here, named."""

    # Each case is a turn that is complete EXCEPT for the one defect
    # under test, so the reason asserted is the reason that fired rather
    # than whichever check happens to run first.
    @pytest.mark.parametrize(
        "body,expected",
        [
            ("not a dict", "expected a JSON object"),
            ({}, "no 'turn' object"),
            (
                {"turn": {"id": "t1", "utterance": "u", "status": "bogus", "message": "m"}},
                "is not one of",
            ),
            (
                {"turn": {"id": "t1", "utterance": "u", "status": "proposal", "message": "m"}},
                "carries no 'query_spec'",
            ),
            (
                {
                    "turn": {
                        "id": "t1",
                        "utterance": "u",
                        "status": "clarification",
                        "message": "m",
                        "query_spec": {"v": 1},
                    }
                },
                "must carry query_spec: null",
            ),
            (
                {
                    "turn": {
                        "id": "t1",
                        "utterance": "u",
                        "status": "clarification",
                        "query_spec": None,
                    }
                },
                "no 'message' string",
            ),
            (
                {
                    "turn": {
                        "id": "t1",
                        "utterance": "u",
                        "status": "clarification",
                        "query_spec": None,
                        "message": "m",
                    },
                    "suspended_turn_ids": "t1",
                },
                "not a list",
            ),
            # An id is what edit_turn_id addresses, so a turn without one
            # survives this boundary only to break rewind later.
            (
                {
                    "turn": {
                        "utterance": "u",
                        "status": "clarification",
                        "query_spec": None,
                        "message": "m",
                    }
                },
                "carries no 'id' string",
            ),
            (
                {
                    "turn": {
                        "id": "   ",
                        "utterance": "u",
                        "status": "clarification",
                        "query_spec": None,
                        "message": "m",
                    }
                },
                "carries no 'id' string",
            ),
            (
                {
                    "turn": {
                        "id": "t1",
                        "status": "clarification",
                        "query_spec": None,
                        "message": "m",
                    }
                },
                "carries no 'utterance' string",
            ),
        ],
    )
    async def test_out_of_contract_response_becomes_error_turn(
        self, hippo_client, exon_configured, monkeypatch, body, expected
    ):
        _install_stub(monkeypatch, response=_StubResponse(body))
        payload = await _call_tool(
            create_mcp_server(hippo_client),
            "converse_query_spec",
            {"utterance": "donors"},
        )
        assert payload["turn"]["status"] == "error"
        assert expected in payload["turn"]["message"]


@pytest.mark.anyio
class TestNeverExecutes:
    async def test_returns_proposal_without_executing(
        self, hippo_client, exon_configured, monkeypatch
    ):
        """A proposal is handed back for a separate explicit execute call —
        this tool must not fetch rows itself (Decision 8, and 'the LLM
        never decides to execute')."""
        hippo_client.create("Donor", {"name": "D1", "sex": "female"})
        _install_stub(
            monkeypatch,
            response=_StubResponse(
                {
                    "turn": {
                        "id": "t1",
                        "utterance": "female donors",
                        "status": "proposal",
                        "query_spec": VALID_SPEC,
                        "message": "All donors.",
                    }
                }
            ),
        )
        calls = []
        original_query = hippo_client.query
        monkeypatch.setattr(
            hippo_client,
            "query",
            lambda *a, **k: (calls.append((a, k)), original_query(*a, **k))[1],
        )
        payload = await _call_tool(
            create_mcp_server(hippo_client),
            "converse_query_spec",
            {"utterance": "female donors"},
        )
        assert payload["turn"]["status"] == "proposal"
        # No rows, no total, no query call.
        assert "items" not in payload
        assert "total" not in payload
        assert calls == []


class TestTimeoutConfig:
    def test_default_timeout(self, monkeypatch):
        from mosaic.mcp.server import DEFAULT_EXON_TIMEOUT_SECONDS, _exon_timeout

        monkeypatch.delenv("MOSAIC_EXON_TIMEOUT", raising=False)
        assert _exon_timeout() == DEFAULT_EXON_TIMEOUT_SECONDS

    @pytest.mark.parametrize("raw", ["not-a-number", "0", "-5", ""])
    def test_bad_values_fall_back_to_default(self, monkeypatch, raw):
        from mosaic.mcp.server import DEFAULT_EXON_TIMEOUT_SECONDS, _exon_timeout

        monkeypatch.setenv("MOSAIC_EXON_TIMEOUT", raw)
        assert _exon_timeout() == DEFAULT_EXON_TIMEOUT_SECONDS

    def test_valid_override_is_used(self, monkeypatch):
        from mosaic.mcp.server import _exon_timeout

        monkeypatch.setenv("MOSAIC_EXON_TIMEOUT", "12.5")
        assert _exon_timeout() == 12.5


@pytest.mark.anyio
class TestTimeoutWiring:
    """The timeout is read at MOUNT time, alongside MOSAIC_EXON_URL, so the
    whole delegate configuration has one lifecycle -- a running server
    cannot be serving an endpoint chosen at startup with a timeout changed
    underneath it."""

    async def test_timeout_reaches_the_http_client(
        self, hippo_client, exon_configured, monkeypatch
    ):
        monkeypatch.setenv("MOSAIC_EXON_TIMEOUT", "7")
        stub = _install_stub(
            monkeypatch,
            response=_StubResponse(
                {
                    "turn": {
                        "id": "t1",
                        "utterance": "donors",
                        "status": "clarification",
                        "query_spec": None,
                        "message": "Which cohort?",
                    }
                }
            ),
        )
        await _call_tool(
            create_mcp_server(hippo_client),
            "converse_query_spec",
            {"utterance": "donors"},
        )
        (init,) = stub.inits
        assert init["timeout"] == 7.0

    async def test_timeout_is_fixed_at_mount_time(
        self, hippo_client, exon_configured, monkeypatch
    ):
        monkeypatch.setenv("MOSAIC_EXON_TIMEOUT", "7")
        server = create_mcp_server(hippo_client)
        # Changed after the server was built: must not take effect until
        # the next mount, the same way MOSAIC_EXON_URL does not.
        monkeypatch.setenv("MOSAIC_EXON_TIMEOUT", "99")
        stub = _install_stub(
            monkeypatch,
            response=_StubResponse(
                {
                    "turn": {
                        "id": "t1",
                        "utterance": "donors",
                        "status": "clarification",
                        "query_spec": None,
                        "message": "Which cohort?",
                    }
                }
            ),
        )
        await _call_tool(server, "converse_query_spec", {"utterance": "donors"})
        (init,) = stub.inits
        assert init["timeout"] == 7.0


@pytest.mark.anyio
class TestRecomputedTurnsPassthrough:
    """`turns` -- the full post-call conversation.

    `turn` + `suspended_turn_ids` is provably insufficient after an edit: the
    planning service recomputes the turns following the edited one, and
    without those a caller derives "the current draft" from its own stale
    copy and executes a pre-edit query.
    """

    async def test_turns_passed_through(self, hippo_client, exon_configured, monkeypatch):
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
        _install_stub(
            monkeypatch,
            response=_StubResponse(
                {"turn": convo[0], "suspended_turn_ids": [], "turns": convo}
            ),
        )
        payload = await _call_tool(
            create_mcp_server(hippo_client),
            "converse_query_spec",
            {"utterance": "cerebellum samples instead", "edit_turn_id": "t1"},
        )
        assert payload["turns"] == convo
        # The recomputed later turn's message is now reachable, which is the
        # whole point -- before this it was computed and discarded.
        assert payload["turns"][1]["message"] == "Cerebellum samples from female donors."

    async def test_absent_turns_stays_absent(self, hippo_client, exon_configured, monkeypatch):
        """Backward compatibility with a planning service that predates the
        field -- and it must stay ABSENT, not become [].

        The tool description tells a caller to replace its turn list with
        the returned `turns`. Coercing absent to [] would tell that caller
        the conversation is now empty, i.e. wipe the chat -- exactly the
        failure the error paths avoid by omitting the field. The success
        path has to follow the same rule against a legacy service.
        """
        _install_stub(
            monkeypatch,
            response=_StubResponse(
                {
                    "turn": {
                        "id": "t1",
                        "utterance": "donors",
                        "status": "clarification",
                        "query_spec": None,
                        "message": "Which cohort?",
                    }
                }
            ),
        )
        payload = await _call_tool(
            create_mcp_server(hippo_client),
            "converse_query_spec",
            {"utterance": "donors"},
        )
        assert "turns" not in payload
        # The rest of the envelope is unaffected.
        assert payload["turn"]["status"] == "clarification"

    async def test_empty_turns_is_passed_through_as_empty(
        self, hippo_client, exon_configured, monkeypatch
    ):
        """The converse of the above: a service that DOES send `turns: []`
        means it, and that is distinguishable from omitting the field."""
        _install_stub(
            monkeypatch,
            response=_StubResponse(
                {
                    "turn": {
                        "id": "t1",
                        "utterance": "donors",
                        "status": "clarification",
                        "query_spec": None,
                        "message": "Which cohort?",
                    },
                    "turns": [],
                }
            ),
        )
        payload = await _call_tool(
            create_mcp_server(hippo_client),
            "converse_query_spec",
            {"utterance": "donors"},
        )
        assert payload["turns"] == []

    async def test_recomputed_proposal_is_revalidated(
        self, hippo_client, exon_configured, monkeypatch
    ):
        """The load-bearing case. A recompute produces a spec this deployment
        has never validated; validating only `turn` would let it through."""
        good = {
            "id": "t1",
            "utterance": "donors",
            "status": "proposal",
            "query_spec": VALID_SPEC,
            "message": "All donors.",
        }
        bad_recompute = {
            "id": "t2",
            "utterance": "by eye colour",
            "status": "proposal",
            "query_spec": {
                "v": 1,
                "anchor": "Donor",
                "mode": "AND",
                "criteria": [
                    {"kind": "field", "slot": "eye_colour", "op": "eq", "value": "blue"}
                ],
            },
            "message": "Filtering by eye colour.",
        }
        _install_stub(
            monkeypatch,
            response=_StubResponse(
                {"turn": good, "suspended_turn_ids": [], "turns": [good, bad_recompute]}
            ),
        )
        payload = await _call_tool(
            create_mcp_server(hippo_client),
            "converse_query_spec",
            {"utterance": "donors", "edit_turn_id": "t1"},
        )
        # `turn` itself was valid, but a recomputed turn was not.
        assert payload["turn"]["status"] == "error"
        assert "recomputed" in payload["turn"]["message"]
        assert "UNKNOWN_SLOT" in payload["turn"]["message"]
        assert "t2" in payload["turn"]["message"]
        # ADR-0010 decision 5 holds on this path too.
        assert EXON_URL not in payload["turn"]["message"]

    async def test_error_omits_turns_rather_than_emptying_them(
        self, hippo_client, exon_configured, monkeypatch
    ):
        """An error means nothing was applied, so the conversation is
        UNCHANGED. Returning [] would tell a caller to wipe the chat."""
        import httpx2

        _install_stub(monkeypatch, raise_exc=httpx2.TimeoutException("t"))
        payload = await _call_tool(
            create_mcp_server(hippo_client),
            "converse_query_spec",
            {"utterance": "donors"},
        )
        assert payload["turn"]["status"] == "error"
        # Absent, not empty -- `in (None, [])` would pass either way and so
        # would not test the invariant this case is named for.
        assert "turns" not in payload

    async def test_malformed_entry_in_turns_is_rejected(
        self, hippo_client, exon_configured, monkeypatch
    ):
        good = {
            "id": "t1",
            "utterance": "donors",
            "status": "proposal",
            "query_spec": VALID_SPEC,
            "message": "All donors.",
        }
        _install_stub(
            monkeypatch,
            response=_StubResponse(
                {
                    "turn": good,
                    "turns": [good, {"status": "clarification", "query_spec": None}],
                }
            ),
        )
        payload = await _call_tool(
            create_mcp_server(hippo_client),
            "converse_query_spec",
            {"utterance": "donors"},
        )
        assert payload["turn"]["status"] == "error"
        assert "turns[1]" in payload["turn"]["message"]

    async def test_recomputed_turn_missing_id_is_rejected(
        self, hippo_client, exon_configured, monkeypatch
    ):
        """The id/utterance check applies to every `turns` entry, not just
        the top-level turn -- a recomputed turn is just as addressable."""
        good = {
            "id": "t1",
            "utterance": "donors",
            "status": "proposal",
            "query_spec": VALID_SPEC,
            "message": "All donors.",
        }
        _install_stub(
            monkeypatch,
            response=_StubResponse(
                {
                    "turn": good,
                    "turns": [
                        good,
                        {
                            "utterance": "and female",
                            "status": "proposal",
                            "query_spec": VALID_SPEC,
                            "message": "Female donors.",
                        },
                    ],
                }
            ),
        )
        payload = await _call_tool(
            create_mcp_server(hippo_client),
            "converse_query_spec",
            {"utterance": "donors"},
        )
        assert payload["turn"]["status"] == "error"
        assert "turns[1]" in payload["turn"]["message"]
        assert "carries no 'id' string" in payload["turn"]["message"]
