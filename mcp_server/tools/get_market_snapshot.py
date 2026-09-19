"""MCP tool: get_market_snapshot. Wraps data.api.get_market_snapshot.

Specified by docs/mcp-tools.md#get_market_snapshot.

Purpose: price, share count and the enterprise-value bridge, all observed at one
instant. Returned as a single object precisely so an agent cannot combine a
price from one moment with a share count from another.

Errors: ValueError for an out-of-scope ticker; a missing snapshot returns None
plus a data_quality gap, never a stale price presented as current.
as_of: required.
"""

from __future__ import annotations

from typing import Any

from mcp_server.backends import require_in_scope
from schema.contracts.tools import GetMarketSnapshotRequest, GetMarketSnapshotResponse


def run(request: GetMarketSnapshotRequest, backends: Any) -> GetMarketSnapshotResponse:
    require_in_scope(request.ticker, request.as_of)

    # None when nothing had been observed by as_of. Deliberately not backfilled
    # with the nearest earlier quote: a stale price presented as current is the
    # kind of error that survives all the way into a valuation.
    snapshot = backends.market.get_snapshot(request.ticker, request.as_of)

    return GetMarketSnapshotResponse(as_of=request.as_of, snapshot=snapshot)
