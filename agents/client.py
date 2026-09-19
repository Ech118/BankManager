"""Anthropic client wrapper: model selection, token accounting, LLM_MODE.

Specified by docs/pipeline.md and docs/roadmap.md Step 5.

LLM_MODE=mock returns the fixtures/mock/analysis_*.json files without calling
the API. That separation from MODE is why P1 and P2 can work on this repo with
no Anthropic key at all, and why the whole contract suite runs offline.

Model choice is per-agent (MODEL_BY_AGENT); override for a run with BM_MODEL.
Every call reports its tokens, because a pipeline of seven LLM calls over filing
text gets expensive quietly (error K).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

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

# $ per 1M tokens (input, output). ASSUMPTION: copied from the claude-api skill's
# price table dated 2026-06-24; used only for run-cost estimates, never for logic.
PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
}

_MOCK_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "mock"

# The mock financial fixture predates per-finding sections; assign them here so
# mock runs exercise the same routing a live run does.
_MOCK_SECTIONS = {
    AgentName.FINANCIAL: ["financials", "earnings_quality", "earnings_quality"],
}


class LLMError(RuntimeError):
    """The call failed, was refused, was truncated or returned unusable output."""


def llm_mode() -> str:
    """`mock` unless LLM_MODE is explicitly `live`. Independent of MODE."""
    return os.environ.get("LLM_MODE", os.environ.get("BM_LLM", "mock")).lower()


def model_for(agent: AgentName) -> str:
    return os.environ.get("BM_MODEL") or MODEL_BY_AGENT[agent]


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Dollar estimate from PRICES. 0.0 for an unpriced model (e.g. 'mock')."""
    price = PRICES.get(model)
    return 0.0 if not price else (tokens_in * price[0] + tokens_out * price[1]) / 1_000_000


def _mock_text(agent: AgentName) -> str:
    path = _MOCK_DIR / f"analysis_{agent.value}.json"
    if not path.exists():
        raise LLMError(f"no mock fixture for agent {agent.value!r} ({path.name})")
    data = json.loads(path.read_text(encoding="utf-8"))
    for finding, section in zip(
        data.get("findings", []), _MOCK_SECTIONS.get(agent, []), strict=False
    ):
        finding.setdefault("section", section)
    return json.dumps(data)


def complete(
    agent: AgentName,
    system: str,
    user: str,
    max_tokens: int = 4096,
    schema: dict | None = None,
) -> dict:
    """One model call. Returns {"text", "model", "tokens_in", "tokens_out", "seconds"}.

    In mock mode, loads this agent's fixture instead of calling the API.
    `schema`, when given, is sent as a JSON-schema structured-output constraint.
    """
    if llm_mode() == "mock":
        return {
            "text": _mock_text(agent),
            "model": "mock",
            "tokens_in": 0,
            "tokens_out": 0,
            "seconds": 0.0,
        }

    import anthropic  # imported lazily so mock mode needs no SDK or key

    model = model_for(agent)
    params: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user}],
        "thinking": {"type": "adaptive"},
    }
    output_config: dict = {}
    if schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": schema}
    if os.environ.get("BM_EFFORT"):
        output_config["effort"] = os.environ["BM_EFFORT"]
    if output_config:
        params["output_config"] = output_config

    t0 = time.monotonic()
    try:
        with anthropic.Anthropic().messages.stream(**params) as stream:
            msg = stream.get_final_message()
    except anthropic.RateLimitError as e:
        raise LLMError(f"{agent.value}: rate limited: {e}") from e
    except anthropic.APIConnectionError as e:
        raise LLMError(f"{agent.value}: network error: {e}") from e
    except anthropic.APIStatusError as e:
        raise LLMError(f"{agent.value}: API error {e.status_code}: {e.message}") from e
    if msg.stop_reason == "refusal":
        raise LLMError(f"{agent.value}: model refused")
    if msg.stop_reason == "max_tokens":
        raise LLMError(f"{agent.value}: output truncated at max_tokens={max_tokens}")
    text = next((b.text for b in msg.content if b.type == "text"), None)
    if text is None:
        raise LLMError(f"{agent.value}: no text block in the response")
    return {
        "text": text,
        "model": model,
        "tokens_in": (msg.usage.input_tokens or 0)
        + (getattr(msg.usage, "cache_read_input_tokens", 0) or 0)
        + (getattr(msg.usage, "cache_creation_input_tokens", 0) or 0),
        "tokens_out": msg.usage.output_tokens or 0,
        "seconds": time.monotonic() - t0,
    }
