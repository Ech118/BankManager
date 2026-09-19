"""MCP tool: get_peer_companies. Wraps data.api.get_peer_companies.

Specified by docs/mcp-tools.md#get_peer_companies.

Purpose: candidate comparables by SIC code and market-cap band, each with a
`selection_reason`. Peer choice moves the valuation more than almost any other
input, so the default list is deterministic; the Valuation Agent may override
it, but must record why (error E).

Errors: ValueError for an out-of-scope ticker. Fewer peers than `limit` is a
valid answer and shows up as a data_quality gap.
as_of: required.

TODO(roadmap Step 3, P1).
"""

from __future__ import annotations

from typing import Any

from schema.contracts.tools import GetPeerCompaniesRequest, GetPeerCompaniesResponse


def run(request: GetPeerCompaniesRequest, backends: Any) -> GetPeerCompaniesResponse:
    raise NotImplementedError("TODO(roadmap Step 3, P1)")
