"""MCP tool: search_filing. Wraps the filing repository's ranked search.

Specified by docs/mcp-tools.md#search_filing and docs/adr/0006.

Purpose: find the section that discusses something, when the agent does not
know which Item it lives in. ALWAYS scoped by ticker and date, optionally by
form and item.

Returns whole sections, not fragments: an agent reasoning about a debt covenant
needs the paragraph around it, and the verifier needs a stable anchor for the
quote it will later string-match.

The index is in process, not Postgres - a run reads one company's filings, and
ranking a few hundred sections locally beats a round trip. ADR 0006's substance
(no chunking, no embeddings, whole sections only) is unaffected; see
data/sections/search.py.

Errors: ValueError for an out-of-scope ticker. Empty list is a valid answer.
as_of: required.
"""

from __future__ import annotations

from typing import Any

from mcp_server.backends import require_in_scope
from schema.contracts.tools import SearchFilingRequest, SearchFilingResponse


def run(request: SearchFilingRequest, backends: Any) -> SearchFilingResponse:
    require_in_scope(request.ticker, request.as_of)

    # One more than asked for, so "exactly limit hits" and "more than limit
    # hits" stay distinguishable - the same reason get_peer_companies does it.
    sections = backends.filings.search_sections(
        request.ticker,
        request.query,
        request.as_of,
        forms=[str(f) for f in request.forms] if request.forms else None,
        items=[str(i) for i in request.items] if request.items else None,
        limit=request.limit + 1,
    )

    truncated = len(sections) > request.limit
    return SearchFilingResponse(
        as_of=request.as_of,
        sections=sections[: request.limit],
        truncated=truncated,
    )
