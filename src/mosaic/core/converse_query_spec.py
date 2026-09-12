"""Shared conversational-turn envelope logic for ``converse_query_spec``
(issue #186, ADR-0010) — reused VERBATIM by every transport that exposes
it: the MCP tool (``mosaic/mcp/server.py``) and the GraphQL
``converseQuerySpec`` mutation (``mosaic/graphql/resolvers.py``, issue
#205). Neither transport reimplements the planning delegation, the
ADR-0010 relay terms, the in-process re-validation of every candidate
spec, or the suspend/recompute semantics — both call :func:`run_converse_turn`
below, which owns all of it; a transport module supplies only its own
argument plumbing (how it gets a ``utterance``/``turns``/... and how it
resolves the live ``MosaicClient``/capability manifest for the request).

This module deliberately imports nothing from ``mcp`` or from
``strawberry``/FastAPI: ``graphql`` and ``mcp`` are separate optional
extras (see ``pyproject.toml``), and this logic must stay importable
under either one alone, or neither.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from mosaic.core.query_spec import QuerySpecShapeError, parse_query_spec
from mosaic.core.query_spec import validate_query_spec as _validate_query_spec
from mosaic.core.schema_typing import EntityCapability

logger = logging.getLogger(__name__)

#: Env var naming Exon's conversational turn endpoint (issue #186). Unset
#: (or blank) means ``converse_query_spec`` is not registered on ANY
#: transport — the same gating philosophy as ``--mcp``/``MOSAIC_SERVE_MCP``:
#: an optional integration is absent, not present-and-broken.
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
#: this envelope is what a client branches on, so an unrecognized status
#: reaching one would be a silent contract break.
_EXON_TURN_STATUSES = frozenset({"proposal", "clarification", "suspended"})

#: What an ``error`` turn calls the delegate. ADR-0010 decision 5: a
#: client-visible failure names the delegate's ROLE, never its address.
#: This surface carries no authn/authz (ADR-0009 item 5), so anything on
#: an error turn is effectively public, and the endpoint URL is deployment
#: topology. The URL and the upstream body go to ``logger`` instead, where
#: an operator can still diagnose the failure.
EXON_ROLE_NAME = "the configured conversational planning service"


def exon_url() -> str:
    """Read the configured Exon endpoint, or ``""`` when unset/blank —
    the one gating condition every transport shares."""
    return os.environ.get(EXON_URL_ENV, "").strip()


def exon_timeout() -> float:
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
    thing standing between an out-of-contract planning service and a
    client's UI: a missing ``status``, an unrecognized one, or a
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
    # ``id`` and ``utterance`` are what make a turn addressable: a caller
    # passes an id back as ``edit_turn_id`` to rewind, and renders the
    # utterance beside the turn. A turn missing either survives this
    # boundary only to break rewind later, in the place this checker
    # exists to keep failures out of. Checked for the same reason as
    # ``status`` and ``message`` -- the alternative is a silent contract
    # break downstream (ADR-0010 decision 3). Applied to every ``turns``
    # entry too, since a recomputed turn is just as addressable.
    if not isinstance(turn.get("id"), str) or not turn["id"].strip():
        return "carries no 'id' string -- it could not be edited or rewound."
    if not isinstance(turn.get("utterance"), str):
        return "carries no 'utterance' string."
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
    back INSIDE the discriminated envelope a client already branches on,
    with ``query_spec: null`` — not as a bare transport-level exception,
    which a chat UI would have no structured way to render next to the
    turns it already drew.

    The turn carries no ``id``: an ``error`` is not a conversational step
    a caller can later rewind to or edit (there is nothing to recompute),
    so minting an id for it would invite exactly that misuse.

    Callers returning this deliberately OMIT ``turns`` rather than sending
    ``[]``. Every error path means nothing was applied, so the conversation
    is *unchanged* — and an empty list would say the opposite ("the
    conversation is now empty"), which a caller that replaces its state
    with the response would act on by wiping the chat. Absent means "no
    authoritative state supplied; keep your own." (A transport whose own
    wire contract has no way to represent "absent" — e.g. GraphQL's
    non-null `turns` — is responsible for translating that itself; see
    ``mosaic/graphql/resolvers.py``'s ``converseQuerySpec`` docstring.)
    """
    return {
        "id": None,
        "utterance": utterance,
        "status": "error",
        "query_spec": None,
        "message": message,
    }


def run_converse_turn(
    *,
    manifest: dict[str, EntityCapability],
    exon_endpoint: str,
    timeout: float,
    utterance: str,
    query_spec: Optional[dict] = None,
    turns: Optional[list[dict]] = None,
    edit_turn_id: Optional[str] = None,
) -> dict[str, Any]:
    """Run one ``converse_query_spec`` turn against Exon and return the
    ``{turn, suspended_turn_ids, [turns]}`` envelope (ADR-0010, design.md
    Decision 8). This is the ONE place that planning delegation happens —
    every transport (MCP, GraphQL) calls this directly rather than
    reimplementing any part of it.

    ``manifest`` is the requesting deployment's capability manifest
    (``mosaic.core.schema_typing.build_capability_manifest``), used only
    to re-validate whatever ``QuerySpec`` Exon returns — Exon is an
    untrusted planner as far as this boundary is concerned, and "Mosaic
    validates before anything executes" has to hold even if Exon's own
    check is stale or bypassed. This never calls ``execute_query_spec`` —
    a ``proposal`` is handed back for a separate, explicit execute call
    once a human confirms it.

    Its client-visible failures name the delegate's *role*, never its
    address (ADR-0010 decision 5): this surface carries no authn, so the
    endpoint URL and any upstream response body go to ``logger`` for the
    operator instead.
    """
    payload = {
        "utterance": utterance,
        "query_spec": query_spec,
        "turns": turns or [],
        "edit_turn_id": edit_turn_id,
    }

    # Import here, not at module scope: httpx2 arrives with the `mcp`
    # extra (the MCP SDK's own HTTP dependency). Keeping it local means a
    # deployment that only installs the `graphql` extra (no `mcp`) can
    # still import this module right up until the first actual call —
    # which only happens once `exon_url()` is non-blank, i.e. a deployment
    # that has explicitly opted into this integration and is expected to
    # have installed whatever it takes to serve it.
    import httpx2

    # ADR-0010 decision 5 governs every `except` below: the client-visible
    # message names the delegate's ROLE (EXON_ROLE_NAME) and never its
    # address, while the URL and any upstream text go to `logger` for the
    # operator. This surface has no authn (ADR-0009 item 5), so an error
    # turn is effectively public; the endpoint is deployment topology and
    # the upstream body is another service's raw output.
    try:
        with httpx2.Client(timeout=timeout) as http:
            response = http.post(exon_endpoint, json=payload)
            response.raise_for_status()
            body = response.json()
    except httpx2.TimeoutException:
        logger.warning(
            "converse_query_spec: no response from %s within %.3gs",
            exon_endpoint,
            timeout,
        )
        return {
            "turn": _error_turn(
                utterance,
                f"{EXON_ROLE_NAME.capitalize()} did not respond within "
                f"{timeout:g}s. The conversation is unchanged -- "
                f"retrying the same utterance is safe.",
            ),
            "suspended_turn_ids": [],
        }
    except httpx2.HTTPStatusError as exc:
        # Exon's own 4xx (e.g. an edit_turn_id it doesn't know, or a
        # query_spec disagreeing with its turn-derived state) is a
        # caller-contract problem, and its body names what disagreed.
        # That detail is genuinely actionable, so it is logged rather than
        # dropped -- but it is the planner's raw text, so the client gets
        # the status code (a stable, Mosaic-authored classification)
        # instead of the body.
        status = getattr(exc.response, "status_code", None)
        logger.warning(
            "converse_query_spec: %s rejected the request (HTTP %s): %s",
            exon_endpoint,
            status,
            (getattr(exc.response, "text", "") or "").strip()[:500] or "<no body>",
        )
        coded = f" (HTTP {status})" if status is not None else ""
        return {
            "turn": _error_turn(
                utterance,
                f"{EXON_ROLE_NAME.capitalize()} rejected the request{coded}. "
                f"The conversation is unchanged; the reason is in the Mosaic "
                f"server log.",
            ),
            "suspended_turn_ids": [],
        }
    except (httpx2.HTTPError, ValueError) as exc:
        # ValueError covers a 2xx body that isn't JSON at all.
        logger.warning(
            "converse_query_spec: could not reach %s: %s: %s",
            exon_endpoint,
            type(exc).__name__,
            exc,
        )
        return {
            "turn": _error_turn(
                utterance,
                f"Could not reach {EXON_ROLE_NAME}. The conversation is "
                f"unchanged; the reason is in the Mosaic server log.",
            ),
            "suspended_turn_ids": [],
        }

    malformed = _reject_malformed_exon_response(body)
    if malformed:
        # The reason is Mosaic-authored (a shape verdict, not upstream
        # prose), so it is safe on the turn -- but log the address too,
        # since "which delegate sent this" is exactly what an operator
        # needs and the turn omits it.
        logger.warning(
            "converse_query_spec: out-of-contract response from %s: %s",
            exon_endpoint,
            malformed,
        )
        return {
            "turn": _error_turn(utterance, malformed),
            "suspended_turn_ids": [],
        }

    turn = body["turn"]
    suspended = body.get("suspended_turn_ids") or []
    # Distinguish "the service sent no turns" from "the service sent an
    # empty conversation". #200 established that an error path must OMIT
    # `turns` rather than send [], because a caller told to "replace your
    # turn list with the returned turns" would read [] as "the
    # conversation is now empty" and wipe the chat. The same reasoning
    # applies on the SUCCESS path against a planning service that predates
    # the field: coercing absent to [] there reintroduces exactly that
    # failure, in the one case #200 set out to stay compatible with. So
    # absent stays absent all the way to the response.
    turns_out = body.get("turns")

    # Re-validate IN-PROCESS (a direct function call, never back through a
    # transport -- same process already hosts the validator, and a
    # self-call would be a needless cycle). Only a `proposal` carries a
    # spec; `clarification`/`suspended` turns have none by contract,
    # already checked above.
    #
    # EVERY proposal is checked, not just `turn`. After an edit, the
    # planning service recomputes the turns following the edited one, so
    # `turns` can carry freshly-generated specs this deployment has never
    # seen -- validating only `turn` would let those reach the caller
    # unchecked, which is exactly the guarantee this re-validation exists
    # to hold.
    for candidate in [turn, *(turns_out or [])]:
        if candidate.get("status") != "proposal":
            continue
        which = (
            "proposed" if candidate is turn
            else f"recomputed (turn id {candidate.get('id')!r})"
        )
        try:
            spec = parse_query_spec(candidate["query_spec"])
        except QuerySpecShapeError as exc:
            # These two messages carry Mosaic's OWN validator output, not
            # upstream prose, and validate_query_spec already returns
            # exactly this detail to clients -- so it stays on the turn (a
            # planner-driven client needs it to retry). Only the address
            # is withheld.
            logger.warning(
                "converse_query_spec: %s %s a malformed QuerySpec (%s at %s)",
                exon_endpoint,
                which,
                exc.code,
                exc.path,
            )
            return {
                "turn": _error_turn(
                    utterance,
                    f"{EXON_ROLE_NAME.capitalize()} {which} a QuerySpec that "
                    f"is not well-formed ({exc.code} at {exc.path}: {exc}). Nothing "
                    f"was applied.",
                ),
                "suspended_turn_ids": [],
            }
        result = _validate_query_spec(spec, manifest)
        if not result.valid:
            codes = "; ".join(f"{e.code} at {e.path}: {e.message}" for e in result.errors)
            logger.warning(
                "converse_query_spec: %s %s a QuerySpec this deployment "
                "rejects: %s",
                exon_endpoint,
                which,
                codes,
            )
            return {
                "turn": _error_turn(
                    utterance,
                    f"{EXON_ROLE_NAME.capitalize()} {which} a QuerySpec that "
                    f"failed validation against this deployment's capabilities: "
                    f"{codes}. Nothing was applied.",
                ),
                "suspended_turn_ids": [],
            }

    envelope: dict[str, Any] = {
        "turn": turn,
        "suspended_turn_ids": list(suspended),
    }
    if turns_out is not None:
        envelope["turns"] = list(turns_out)
    return envelope
