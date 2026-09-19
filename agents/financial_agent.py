"""Financial Agent: is the reported profit real?

Specified by docs/pipeline.md. Prompt: prompts/financial.md.
Owns ResearchState sections: financials, balance_sheet, cash_flow, earnings_quality.

Runs in PARALLEL with the Business Agent; neither sees the other's output, so
two independent readings of the same company exist before anything is
reconciled.

Its actual question is narrower than "are the financials good": it is whether
the reported numbers describe the business. Specifically:
  - one-time items treated as recurring, or the reverse
  - the gap between GAAP and adjusted figures, and what lives in it
  - working capital: receivables or inventory growing faster than revenue
  - EPS growth from buybacks and tax rates rather than from operations
  - free cash flow that does not follow reported net income

The arithmetic is already done - calc/ computed every metric before this agent
ran. Its job is to say which of those numbers matter and why.

TODO(roadmap Step 1, P3).
"""

from __future__ import annotations

from agents.base import Agent
from schema.contracts.enums import AgentName


class FinancialAgent(Agent):
    """Earnings quality and financial condition."""

    name = AgentName.FINANCIAL
    prompt_file = "financial.md"
    tools = (
        "get_financial_facts",
        "get_filing_section",
        "search_filing",
        "resolve_fact",
    )

    def run(self, context: dict):
        raise NotImplementedError("TODO(roadmap Step 1, P3)")
