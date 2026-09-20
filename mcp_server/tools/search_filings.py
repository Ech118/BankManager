"""MCP tool: search_filings. Wraps the FilingRepository.

Specified by docs/mcp-tools.md#search_filings.

Purpose: let an agent see which filings exist before asking for their contents,
so it fetches two sections rather than a whole 10-K (cost control, error K).
Errors: ValueError for an out-of-scope ticker. Empty list is a valid answer.
as_of: required; filings filed after it are invisible.
"""

from __future__ import annotations

from typing import Any

from mcp_server.backends import require_in_scope
from schema.contracts.tools import SearchFilingsRequest, SearchFilingsResponse


def run(request: SearchFilingsRequest, backends: Any) -> SearchFilingsResponse:
    require_in_scope(request.ticker, request.as_of)

    # Fetched unsliced so `truncated` can say whether `limit` actually cut
    # anything. Asking the repository to slice would make "exactly `limit` rows"
    # and "more than `limit` rows" indistinguishable here.
    filings = backends.filings.search_filings(
        request.ticker,
        request.as_of,
        forms=[str(f) for f in request.forms] if request.forms else None,
        limit=0,
    )

    truncated = len(filings) > request.limit
    return SearchFilingsResponse(
        as_of=request.as_of,
        filings=filings[: request.limit],
        truncated=truncated,
    )
