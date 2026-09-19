"""MCP tool: search_filings. Wraps data.api.search_filings.

Specified by docs/mcp-tools.md#search_filings.

Purpose: let an agent see which filings exist before asking for their contents,
so it fetches two sections rather than a whole 10-K (cost control, error K).
Errors: ValueError for an out-of-scope ticker. Empty list is a valid answer.
as_of: required; filings filed after it are invisible.

TODO(roadmap Step 3, P1).
"""

from __future__ import annotations

from typing import Any

from schema.contracts.tools import SearchFilingsRequest, SearchFilingsResponse


def run(request: SearchFilingsRequest, backends: Any) -> SearchFilingsResponse:
    raise NotImplementedError("TODO(roadmap Step 3, P1)")
