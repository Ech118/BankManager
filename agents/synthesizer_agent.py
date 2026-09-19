"""Synthesizer: the thesis, and the answer to the Red Team.

Specified by docs/pipeline.md. Prompt: prompts/synthesizer.md.
Owns ResearchState section: decision.

Runs LAST among the agents, after the Red Team and before audit.

WHAT IT DOES, given that the report is templated from ResearchState (ADR 0004)
and the Report Generator does all assembly. Five jobs remain, and no other
component owns any of them:

  1. the thesis - two to four sentences a reader could act on
  2. answering the Red Team, point by point. This is the load-bearing one: a
     red team nobody must respond to changes nothing
  3. choosing the primary catalyst and the biggest risk from the candidates the
     other agents raised, which means judging which of several true things
     matters most
  4. the $10,000 answer and its reason
  5. reconciling contradictions between sections into one stated position

WHAT IT MAY NOT DO:
  - emit any number. Scores, probabilities and returns come from calc/
  - render the document. The Report Generator does that deterministically
  - contradict calc/. Its verdict word must satisfy validate_consistency, so a
    "strong_buy" over an expected return below the index fails the audit

Everything it writes lands in ResearchState.decision as Claims with fact_ids,
like any other agent's output.

TODO(roadmap Step 5, P3).
"""

from __future__ import annotations

from agents.base import Agent
from schema.contracts.enums import AgentName


class SynthesizerAgent(Agent):
    """Thesis, red-team response, catalyst and risk selection, the verdict word."""

    name = AgentName.SYNTHESIZER
    prompt_file = "synthesizer.md"
    tools = ("resolve_fact",)
    """Deliberately narrow. By this point every fact it needs is already in the
    state; it resolves citations, it does not gather new evidence."""

    def run(self, context: dict):
        """`context` carries every section, the red team's case, and the
        ScenarioResult whose numbers it must quote verbatim."""
        raise NotImplementedError("TODO(roadmap Step 5, P3)")
