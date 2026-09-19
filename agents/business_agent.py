"""Business Agent: is there a moat, and does management deliver?

Specified by docs/pipeline.md. Prompt: prompts/business.md.
Owns ResearchState sections: company, management, competitive_position, catalysts.

Runs in PARALLEL with the Financial Agent.

Merges what the original plan split into a business analyst and a management
analyst, because the evidence is the same evidence: the filings' own language
about competition, pricing and guidance.

Its questions:
  - pricing power, switching costs, and whether either is visible in the numbers
  - competitive position and what changed since the last filing
  - guidance wording changes between filings, which usually precede a miss
  - past guidance against actual results
  - concrete catalysts, with the filing passage that supports each

This agent does the most qualitative work, so it is held hardest to the citation
rule: every claim cites a quote, and the verifier string-matches it.

TODO(roadmap Step 3, P3).
"""

from __future__ import annotations

from agents.base import Agent
from schema.contracts.enums import AgentName


class BusinessAgent(Agent):
    """Moat, competition, management credibility, catalysts."""

    name = AgentName.BUSINESS
    prompt_file = "business.md"
    tools = (
        "get_filing_section",
        "search_filing",
        "get_company_profile",
        "search_news",
        "resolve_fact",
    )

    def run(self, context: dict):
        raise NotImplementedError("TODO(roadmap Step 3, P3)")
