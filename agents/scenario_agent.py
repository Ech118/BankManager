"""Scenario Agent: bear, base and bull inputs, with reasons.

Specified by docs/pipeline.md. Prompt: prompts/scenario.md.
Owns ResearchState sections: scenarios, sp500_comparison.

PROPOSES INPUTS, DECIDES NOTHING. For each case it supplies revenue CAGR,
terminal margin, EPS at the horizon and an exit multiple, plus a requested
weight and a requested tilt to the prior - each with a written rationale.

calc/ then decides what is used:
  - weights are clamped into a band around the defaults, and every clamp is
    recorded (amendment 1);
  - the prior shift is capped, and requested is recorded alongside applied.

This agent never emits P(beat S&P), never emits a score, and never computes a
price target. Those come from calc.evaluate_scenarios, because a probability an
LLM states directly moves between runs on identical inputs (error C).

The weight rationale is not a formality. It is what a reader uses to judge
whether a 45% bear case is argued or merely asserted.

TODO(roadmap Step 5, P3).
"""

from __future__ import annotations

from agents.base import Agent
from schema.contracts.enums import AgentName


class ScenarioAgent(Agent):
    """Bear/base/bull inputs, requested weights, requested prior shift."""

    name = AgentName.SCENARIO
    prompt_file = "scenario.md"
    tools = (
        "calculate_valuation",
        "get_financial_facts",
        "get_filing_section",
        "resolve_fact",
    )

    def run(self, context: dict):
        raise NotImplementedError("TODO(roadmap Step 5, P3)")
