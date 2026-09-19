"""MCP tool: get_market_snapshot. Wraps data.api.get_market_snapshot.

Specified by docs/mcp-tools.md#get_market_snapshot.

Purpose: price, share count and the enterprise-value bridge, all observed at one
instant. Returned as a single object precisely so an agent cannot combine a
price from one moment with a share count from another.

Errors: ValueError for an out-of-scope ticker; a missing snapshot returns None
plus a data_quality gap, never a stale price presented as current.
as_of: required.

TODO(roadmap Step 1, P1).
"""

from __future__ import annotations

from typing import Any

from schema.contracts.tools import GetMarketSnapshotRequest, GetMarketSnapshotResponse


def run(request: GetMarketSnapshotRequest, backends: Any) -> GetMarketSnapshotResponse:
    raise NotImplementedError("TODO(roadmap Step 1, P1)")
