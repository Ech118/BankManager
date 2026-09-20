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
    AgentName.BUSINESS: ["competitive_position", "competitive_position", "company"],
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


_MOCK_VERIFIER = json.dumps(
    {
        "verdict": "not_supported",
        "reason": "mock verifier: no model available, so nothing is vouched for",
    }
)
"""The offline verifier never vouches for a claim: precision over recall (prompts/verifier.md)."""


_MDNA = "src:edgar:0001234567-26-000010:mdna"
_GUIDANCE = "we expect revenue growth of 8% to 10% and operating margin of 16% to 17%"


def _mock_valuation_plan() -> str:
    """Methods and peers as the Valuation Agent's planning call would choose them (offline)."""
    peers = json.loads((_MOCK_DIR / "peers.json").read_text(encoding="utf-8"))
    return json.dumps(
        {
            "methods": [
                {
                    "name": "pe",
                    "reason": "Earnings are representative and the peers are profitable.",
                },
                {"name": "p_fcf", "reason": "Free cash flow is the hardest figure to flatter."},
                {"name": "peer_median", "reason": "Compare against the median, not a single peer."},
                {
                    "name": "reverse_dcf",
                    "reason": "The expectations reading needs what the price implies.",
                },
            ],
            "peers": [
                {"ticker": p["ticker"], "reason": "Kept from the deterministic default list."}
                for p in peers
            ],
            "notes": "Default peer set kept; no peer added or removed.",
        }
    )


def _mock_valuation_analysis() -> str:
    """analysis_valuation.json routed to `expectations`, plus a P/E-premium finding for `valuation`."""
    data = json.loads((_MOCK_DIR / "analysis_valuation.json").read_text(encoding="utf-8"))
    for f in data["findings"]:
        f.pop("numbers", None)
        f["section"] = "expectations"
        f["calc_refs"] = ["reverse_dcf.implied_fcf_cagr"]
        f["fact_ids"] = ["fact:ACME:fcf:FY2025"]
    data["findings"].append(
        {
            "claim": "The shares trade at a premium to the peer median on trailing earnings.",
            "trend": "structurally_negative",
            "section": "valuation",
            "evidence": [{"quote": _GUIDANCE, "source_id": _MDNA}],
            "calc_refs": ["metrics.valuation.vs_peers.pe_premium"],
            "fact_ids": ["fact:ACME:eps_diluted:FY2025"],
            "confidence": "medium",
        }
    )
    return json.dumps(data)


def _fixture(name: str) -> dict:
    return json.loads((_MOCK_DIR / name).read_text(encoding="utf-8"))


def _finding(
    claim: str, trend: str, section: str, quote: str, source_id: str, confidence: str = "medium"
) -> dict:
    return {
        "claim": claim,
        "trend": trend,
        "section": section,
        "confidence": confidence,
        "fact_ids": [],
        "evidence": [{"quote": quote, "source_id": source_id}],
    }


def _mock_scenario() -> str:
    """The frozen scenarios.json as a Scenario Agent output: no eps (calc derives it), no numerals in prose."""
    sc = _fixture("scenarios.json")
    cases = {}
    for name, c in sc["scenarios"].items():
        cases[name] = {
            "probability": c["probability"],
            "probability_rationale": c["probability_rationale"],
            "horizon_years": c["horizon_years"],
            "revenue_cagr": c["revenue_cagr"]["value"],
            "terminal_margin": c["terminal_margin"]["value"],
            "exit_multiple": c["exit_multiple"]["value"],
            "rationale": c["rationale"],
            "evidence": c["evidence"],
        }
    risk = "src:edgar:0001234567-26-000010:risk_factors"
    findings = [
        _finding(
            "The bear case is a coherent story: bundled competitor pricing squeezes mid-market margin.",
            "structurally_negative",
            "scenarios",
            "could reduce our gross margin by up to 150 basis points",
            risk,
        ),
        _finding(
            "The base case is roughly what management guides to, with the multiple normalising.",
            "neutral",
            "scenarios",
            _GUIDANCE,
            _MDNA,
        ),
        _finding(
            "The bull case needs software mix and switching costs to keep compounding.",
            "temporarily_positive",
            "scenarios",
            "Customers who adopted our software platform renewed at a rate of 94%",
            "src:edgar:0001234567-26-000010:business",
        ),
    ]
    return json.dumps(
        {
            "analysis": {
                "summary": "Three distinct futures; the base case tracks guidance and the multiple de-rates.",
                "findings": findings,
            },
            "scenarios": cases,
            "prior_shift": {
                "value": sc["prior_shift"]["value"],
                "reason": sc["prior_shift"]["reason"],
            },
        }
    )


def _mock_red_team() -> str:
    rt = _fixture("analysis_red_team.json")
    findings = [
        {
            **{k: f[k] for k in ("claim", "trend", "evidence", "confidence")},
            "section": "risks",
            "fact_ids": [],
        }
        for f in rt["findings"]
    ]
    return json.dumps(
        {
            "analysis": {"summary": rt["summary"], "findings": findings},
            "drawdown_path": _fixture("verdict.json")["red_team"]["drawdown_path"],
            "prior_shift": {
                "value": 0,
                "reason": "The scenario agent already tilted the prior down.",
            },
        }
    )


def _mock_synthesizer() -> str:
    """Prose only, with no numerals. Cites quotes the other mock agents already carry."""
    rt = _fixture("analysis_red_team.json")
    debt = rt["findings"][1]["evidence"][0]
    findings = [
        _finding(
            "The business is sound, but the price already discounts more growth than guidance supports.",
            "structurally_negative",
            "decision",
            _GUIDANCE,
            _MDNA,
        ),
        _finding(
            "The refinancing risk is real but manageable, so it does not change the verdict.",
            "neutral",
            "decision",
            debt["quote"],
            debt["source_id"],
        ),
    ]
    return json.dumps(
        {
            "analysis": {
                "summary": "Good business, wrong price: hold the index instead.",
                "findings": findings,
            },
            "synthesis": {
                "thesis": (
                    "Acme is a good business with real switching costs. The market is pricing years of "
                    "growth that guidance does not support. Even the base case trails the index as the "
                    "multiple falls, so we would wait for a much lower price."
                ),
                "primary_catalyst": "A shift toward software that lifts gross margin.",
                "biggest_risk": "The multiple compresses even if guidance is met.",
                "valuation": "expensive",
                "business_quality": "good",
                "financial_strength": "strong",
                "verdict": "avoid",
                "ten_thousand_dollar_answer": {
                    "choice": "sp500",
                    "reason": "The probability-weighted return is below the index assumption and the base case only breaks even.",
                },
                "red_team_responses": (
                    "R1: Accepted. Valuation risk is the dominant issue and drives the avoid. "
                    "R2: Rebutted. The refinancing is low risk given ample interest coverage."
                ),
            },
        }
    )


def _mock_text(agent: AgentName, kind: str = "analysis") -> str:
    if agent is AgentName.VERIFIER:
        return _MOCK_VERIFIER
    if agent is AgentName.VALUATION:
        return _mock_valuation_plan() if kind == "plan" else _mock_valuation_analysis()
    if agent is AgentName.SCENARIO:
        return _mock_scenario()
    if agent is AgentName.RED_TEAM:
        return _mock_red_team()
    if agent is AgentName.SYNTHESIZER:
        return _mock_synthesizer()
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
    kind: str = "analysis",
) -> dict:
    """One model call. Returns {"text", "model", "tokens_in", "tokens_out", "seconds"}.

    In mock mode, loads this agent's fixture instead of calling the API.
    `schema`, when given, is sent as a JSON-schema structured-output constraint.
    """
    if llm_mode() == "mock":
        return {
            "text": _mock_text(agent, kind),
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
