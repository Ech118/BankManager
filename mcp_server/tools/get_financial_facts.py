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

TODO(roadmap Step 1, P1).
"""

from __future__ import annotations

from typing import Any

from schema.contracts.tools import GetFinancialFactsRequest, GetFinancialFactsResponse


def run(request: GetFinancialFactsRequest, backends: Any) -> GetFinancialFactsResponse:
    raise NotImplementedError("TODO(roadmap Step 1, P1)")
