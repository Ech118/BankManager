"""MCP tool: get_filing_section. Wraps data.api.get_filing_section.

Specified by docs/mcp-tools.md#get_filing_section.

Purpose: fetch one structural section verbatim, by id.
Errors: KeyError for an unknown id, or for a section filed after `as_of`.
as_of: required; a section from the future is an error, not an empty result,
because silently returning nothing would look like the filing did not exist.

The returned text is wrapped as quoted DATA by the server. Agents are told, in
every prompt, never to follow instructions found inside it (error F).

TODO(roadmap Step 3, P1).
"""

from __future__ import annotations

from typing import Any

from schema.contracts.tools import GetFilingSectionRequest, GetFilingSectionResponse


def run(request: GetFilingSectionRequest, backends: Any) -> GetFilingSectionResponse:
    raise NotImplementedError("TODO(roadmap Step 3, P1)")
