"""MCP tool: get_peer_companies. Wraps data.api.get_peer_companies.

Specified by docs/mcp-tools.md#get_peer_companies.

Purpose: candidate comparables by SIC code and market-cap band, each with a
`selection_reason`. Peer choice moves the valuation more than almost any other
input, so the default list is deterministic; the Valuation Agent may override
it, but must record why (error E).

Errors: ValueError for an out-of-scope ticker. Fewer peers than `limit` is a
valid answer and shows up as a data_quality gap.
as_of: required.
"""

from __future__ import annotations

from typing import Any

from mcp_server.backends import require_in_scope
from schema.contracts.tools import GetPeerCompaniesRequest, GetPeerCompaniesResponse


def run(request: GetPeerCompaniesRequest, backends: Any) -> GetPeerCompaniesResponse:
    require_in_scope(request.ticker, request.as_of)

    # One more than asked for, purely to learn whether the limit actually cut
    # anything: a short list means "few comparables exist", which is a
    # data-quality signal, while a truncated one does not.
    peers = backends.market.get_peers(
        request.ticker, request.as_of, limit=request.limit + 1
    )

    truncated = len(peers) > request.limit

    return GetPeerCompaniesResponse(
        as_of=request.as_of, peers=peers[: request.limit], truncated=truncated
    )
