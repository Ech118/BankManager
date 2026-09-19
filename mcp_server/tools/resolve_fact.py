"""MCP tool: resolve_fact. Wraps data.api.resolve_fact.

Specified by docs/mcp-tools.md#resolve_fact.

Purpose: turn a fact_id back into the fact. Used by agents checking a citation
before making it, and by the verifier checking one after the fact.

Returns the fact even when it is superseded or post-dates `as_of`, and flags
both conditions, because the verifier needs to tell three cases apart:
  - the id does not exist            -> IssueType.UNRESOLVED_FACT
  - it exists but was restated       -> IssueType.SUPERSEDED_FACT
  - it exists but is from the future -> IssueType.FUTURE_FACT
Collapsing those into "not found" would make the verifier's report useless.

Errors: KeyError for an unknown fact_id.
as_of: required, and used to set `is_future`.

TODO(roadmap Step 1, P1).
"""

from __future__ import annotations

from typing import Any

from schema.contracts.tools import ResolveFactRequest, ResolveFactResponse


def run(request: ResolveFactRequest, backends: Any) -> ResolveFactResponse:
    raise NotImplementedError("TODO(roadmap Step 1, P1)")
