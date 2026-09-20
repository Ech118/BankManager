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

Errors: none. An unknown fact_id is answered with `fact: null` and both flags
false - that IS the UNRESOLVED_FACT case, and raising would collapse it into
the same outcome as the other two, which is exactly what this tool exists to
prevent (docs/mcp-tools.md#resolve_fact).

as_of: required, and used to set `is_future`.
"""

from __future__ import annotations

from typing import Any

from schema.contracts.tools import ResolveFactRequest, ResolveFactResponse


def run(request: ResolveFactRequest, backends: Any) -> ResolveFactResponse:
    # Deliberately NOT the Protocol's resolve_fact, which hides anything filed
    # after as_of. The verifier has to see a future fact in order to report it
    # as one.
    fact = backends.facts.lookup_regardless_of_date(request.fact_id)
    if fact is None:
        return ResolveFactResponse(as_of=request.as_of, fact=None)

    is_future = not backends.facts.is_visible_at(request.fact_id, request.as_of)

    # "Superseded" is relative to as_of, not to today. The as-filed FY2024 cash
    # flow was the current figure until the FY2025 10-K restated it; a run dated
    # before that must not be told it cited a corrected number (ADR 0003).
    is_superseded = bool(
        fact.superseded_by
        and backends.facts.is_visible_at(fact.superseded_by, request.as_of)
    )

    return ResolveFactResponse(
        as_of=request.as_of,
        fact=fact,
        is_superseded=is_superseded,
        is_future=is_future,
    )
