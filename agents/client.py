"""Anthropic client wrapper: model selection, token accounting, LLM_MODE.

Specified by docs/pipeline.md and docs/roadmap.md Step 5.

LLM_MODE=mock returns the fixtures/mock/analysis_*.json files without calling
the API. That separation from MODE is why P1 and P2 can work on this repo with
no Anthropic key at all, and why the whole contract suite runs offline.

Model choice is per-agent. The verifier and the scenario agent do narrow,
well-specified work and do not need the largest model; the synthesizer and red
team do the hardest reasoning. Every call's tokens are logged, because a
pipeline of seven LLM calls over filing text gets expensive quietly (error K).

TODO(roadmap Step 1, P3).
"""

from __future__ import annotations

import os

from schema.contracts.enums import AgentName

DEFAULT_MODEL = "claude-sonnet-5"
"""Default for most agents."""

MODEL_BY_AGENT: dict[AgentName, str] = {
    AgentName.FINANCIAL: DEFAULT_MODEL,
    AgentName.BUSINESS: DEFAULT_MODEL,
    AgentName.VALUATION: DEFAULT_MODEL,
    AgentName.SCENARIO: DEFAULT_MODEL,
    AgentName.RED_TEAM: DEFAULT_MODEL,
    AgentName.SYNTHESIZER: DEFAULT_MODEL,
    AgentName.VERIFIER: "claude-haiku-4-5-20251001",
}
"""Per-agent model. The verifier's check is narrow, so it runs on a cheaper model.

TODO(roadmap Step 5, P3): revisit once per-run cost is measured.
"""


def llm_mode() -> str:
    """`mock` unless LLM_MODE is explicitly `live`. Independent of MODE."""
    return os.environ.get("LLM_MODE", os.environ.get("BM_LLM", "mock")).lower()


def complete(agent: AgentName, system: str, user: str, max_tokens: int = 4096) -> dict:
    """One model call. Returns the text plus token counts.

    In mock mode, loads this agent's fixture instead of calling the API.
    """
    raise NotImplementedError("TODO(roadmap Step 1, P3)")
