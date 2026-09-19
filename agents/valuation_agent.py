"""Valuation Agent: what does today's price already assume?

Specified by docs/pipeline.md. Prompt: prompts/valuation.md.
Owns ResearchState sections: valuation, expectations.

Runs AFTER the financial and business agents, and reads both.

CHOOSES, NEVER COMPUTES. It picks the methods and the peers and justifies both,
then calls calculate_valuation for every number. A P/E it works out itself is a
defect, not a shortcut (ADR 0001).

Its most valuable output is the expectations section: the reverse DCF says what
growth the current price implies, and this agent judges whether the filings
support that. "Is it worth $50?" mostly returns the analyst's own assumptions;
"what would have to be true for $50 to be right?" is a question the evidence can
actually answer.

Peer choice moves the result more than almost any other input, so a peer set
that differs from the deterministic default needs a stated reason (error E).

TODO(roadmap Step 4, P3).
"""

from __future__ import annotations

from agents.base import Agent
from schema.contracts.enums import AgentName


class ValuationAgent(Agent):
    """Method and peer selection, multiples, and the reverse-DCF reading."""

    name = AgentName.VALUATION
    prompt_file = "valuation.md"
    tools = (
        "calculate_valuation",
        "get_peer_companies",
        "get_market_snapshot",
        "get_financial_facts",
        "get_filing_section",
        "resolve_fact",
    )

    def run(self, context: dict):
        raise NotImplementedError("TODO(roadmap Step 4, P3)")
