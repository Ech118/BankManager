"""Red Team: argue the bear case, from the raw facts.

Specified by docs/pipeline.md. Prompt: prompts/red_team.md.
Owns ResearchState section: risks.

Runs AFTER the Scenario Agent and BEFORE audit.

WHY IT EXISTS. A pipeline of agents asked to analyse a company drifts optimistic:
each one is reading the company's own filings, written by people making a case,
and nothing in the chain is rewarded for disagreeing. The Red Team is the one
component whose job is to be unimpressed.

IT GETS THE RAW FACT SHEET, not the other agents' summaries. If it only saw
their conclusions it would restate them in a sceptical tone, which looks like
disagreement and is not. Reading the source independently is what lets it find
something they missed (error J).

What it produces:
  - the strongest case against the leading view
  - the most plausible path to a 30%+ drawdown
  - additional risks for the risks section
  - optionally, a requested DOWNWARD prior shift with a reason, which calc/
    applies within the same cap as the Scenario Agent's

The Synthesizer is then REQUIRED to answer it. A red team nobody has to respond
to is theatre.

TODO(roadmap Step 5, P3).
"""

from __future__ import annotations

from agents.base import Agent
from schema.contracts.enums import AgentName


class RedTeamAgent(Agent):
    """The bear case, argued from source rather than from summaries."""

    name = AgentName.RED_TEAM
    prompt_file = "red_team.md"
    tools = (
        "get_financial_facts",
        "get_filing_section",
        "search_filing",
        "search_news",
        "resolve_fact",
    )

    def run(self, context: dict):
        """`context` carries the RAW factsheet and metrics, plus the other
        agents' outputs for reference - in that order of priority."""
        raise NotImplementedError("TODO(roadmap Step 5, P3)")
