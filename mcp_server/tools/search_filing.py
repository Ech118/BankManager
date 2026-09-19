"""MCP tool: search_filing. Wraps data.api.search_filing.

Specified by docs/mcp-tools.md#search_filing and docs/adr/0006.

Purpose: find the section that discusses something, when the agent does not know
which Item it lives in. Postgres full-text search, ALWAYS scoped by ticker and
date and optionally by form and item.

Returns whole sections, not fragments: an agent reasoning about a debt covenant
needs the paragraph around it, and the verifier needs a stable anchor for the
quote it will later string-match.

Errors: ValueError for an out-of-scope ticker. Empty list is a valid answer.
as_of: required.

TODO(roadmap Step 3, P1).
"""

from __future__ import annotations

from typing import Any

from schema.contracts.tools import SearchFilingRequest, SearchFilingResponse


def run(request: SearchFilingRequest, backends: Any) -> SearchFilingResponse:
    raise NotImplementedError("TODO(roadmap Step 3, P1)")
