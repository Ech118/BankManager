"""Shared agent machinery: prompt assembly, schema-validated output, retries.

Specified by docs/pipeline.md and docs/research-state.md.

Every agent goes through here, so the invariants hold for all of them rather
than depending on each prompt remembering:

  - OUTPUT IS VALIDATED against Analysis before it is accepted. Invalid output
    is retried once with the validation error fed back, then fails loudly with
    the raw text logged. An LLM occasionally emits malformed JSON; silently
    dropping it would lose a section with no trace.

  - FINDINGS WITHOUT EVIDENCE ARE DROPPED and logged. The contract already
    rejects them, so this is the visible-failure path rather than a crash
    (error I).

  - FILING TEXT IS WRAPPED as quoted data with an explicit instruction not to
    follow anything inside it (error F).

  - THE REDACT HOOK is applied to every piece of filing text before it reaches
    the model, so the backtest's anonymization cannot be bypassed by an agent
    fetching its own text (error A).

TODO(roadmap Step 1, P3).
"""

from __future__ import annotations

from collections.abc import Callable

from schema.contracts.analysis import Analysis
from schema.contracts.claims import Claim
from schema.contracts.enums import AgentName
from schema.contracts.interfaces import McpClient

MAX_OUTPUT_RETRIES = 1
"""Reprompts on invalid output. One, then fail loudly with the raw text logged."""


class Agent:
    """Base class for every agent in the roster."""

    name: AgentName
    prompt_file: str
    tools: tuple[str, ...] = ()
    """MCP tools this agent may call. Narrower is cheaper and safer."""

    def __init__(self, mcp: McpClient, redact: Callable[[str], str] | None = None) -> None:
        self.mcp = mcp
        self.redact = redact
        raise NotImplementedError("TODO(roadmap Step 1, P3)")

    def build_prompt(self, context: dict) -> str:
        """Assemble system rules, the agent prompt, and the wrapped context."""
        raise NotImplementedError("TODO(roadmap Step 1, P3)")

    def wrap_untrusted(self, text: str, source_id: str) -> str:
        """Wrap filing or news text as quoted DATA, after applying `redact`."""
        raise NotImplementedError("TODO(roadmap Step 1, P3)")

    def run(self, context: dict) -> Analysis:
        """Call the model, validate against Analysis, retry once on invalid output."""
        raise NotImplementedError("TODO(roadmap Step 1, P3)")

    def to_claims(self, analysis: Analysis) -> list[Claim]:
        """Convert findings into Claims for this agent's ResearchState section.

        Where the no-bare-numbers rule bites: a finding whose number carries no
        fact_id cannot become a Claim, and is dropped and logged.
        """
        raise NotImplementedError("TODO(roadmap Step 1, P3)")
