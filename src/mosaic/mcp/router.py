"""ASGI mounting for the MCP transport.

Produces the Streamable HTTP ASGI app for :func:`mosaic.mcp.create_mcp_app`,
mounted onto the existing ``mosaic serve`` app at ``/mcp`` (see
``mosaic.serve.create_default_app`` and the ``mosaic serve --mcp`` flag).

Mosaic holds zero authn/authz (issue #54 Part A) — same posture as REST
and GraphQL, confirmed acceptable for this surface in #185.
"""

from __future__ import annotations

from typing import Any

from mosaic.core.client import MosaicClient
from mosaic.mcp.server import create_mcp_server


def create_mcp_app(hippo_client: MosaicClient) -> tuple[Any, Any]:
    """Build ``(mcp_server, asgi_app)`` for one Mosaic deployment.

    ``stateless_http``/``json_response`` are both True: the resources
    exposed so far (#182) carry no per-session state, so the simpler
    request/response shape is preferable to standing up SSE streaming
    machinery nothing here needs yet. A future stateful tool (if one ever
    needs session-scoped state) would revisit this.
    """
    mcp = create_mcp_server(hippo_client)
    asgi_app = mcp.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
    )
    return mcp, asgi_app
