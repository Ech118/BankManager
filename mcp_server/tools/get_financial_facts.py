"""MCP tool: get_financial_facts. Wraps data.api.get_financial_facts.

Specified by docs/mcp-tools.md#get_financial_facts.

Purpose: the main way an agent obtains numbers. Returns FinancialFact rows with
fact_ids, which is what the agent then cites; it never retypes the number into
prose unsourced (principle 2).

Restated values are EXCLUDED by default. An agent has to ask for
`include_superseded` explicitly, so citing a corrected number is a deliberate
act the verifier can flag (IssueType.SUPERSEDED_FACT).

Errors: ValueError for an out-of-scope ticker. Unknown metric names yield no
rows rather than an error, and the gap shows up in data_quality.
as_of: required.
"""

from __future__ import annotations

from typing import Any

from mcp_server.backends import require_in_scope
from schema.contracts.tools import GetFinancialFactsRequest, GetFinancialFactsResponse


def run(request: GetFinancialFactsRequest, backends: Any) -> GetFinancialFactsResponse:
    require_in_scope(request.ticker, request.as_of)

    # Fetched unsliced so `truncated` can say whether `periods` actually cut
    # anything. Asking the repository to slice would make "exactly `periods`
    # rows" and "more than `periods` rows" indistinguishable here.
    facts = backends.facts.get_facts(
        request.ticker,
        request.metrics,
        request.as_of,
        period_type=request.period_type,
        include_superseded=request.include_superseded,
    )

    truncated = request.periods is not None and len(facts) > request.periods
    if request.periods is not None:
        facts = facts[: request.periods]

    return GetFinancialFactsResponse(
        as_of=request.as_of, facts=facts, truncated=truncated
    )
