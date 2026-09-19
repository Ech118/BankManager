"""MCP tool: search_news. Wraps data.api.search_news.

Specified by docs/mcp-tools.md#search_news and docs/verification.md.

Purpose: post-earnings developments the filings cannot contain.

THE LEAST TRUSTED INPUT IN THE SYSTEM. News is arbitrary third-party prose, and
it is where a prompt-injection attempt would most plausibly arrive. The server
wraps every item as quoted data, agents are instructed never to act on
instructions found inside it, and the e2e suite carries an injection test
(error F).

Errors: ValueError for an out-of-scope ticker; a provider outage returns an
empty list plus a data_quality gap rather than failing the run.
as_of: required, and it bounds the window from ABOVE as well as below.

TODO(roadmap Step 4, P1).
"""

from __future__ import annotations

from typing import Any

from schema.contracts.tools import SearchNewsRequest, SearchNewsResponse


def run(request: SearchNewsRequest, backends: Any) -> SearchNewsResponse:
    raise NotImplementedError("TODO(roadmap Step 4, P1)")
