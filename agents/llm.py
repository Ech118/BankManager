"""LLM access for the agents. Three implementations behind one interface:

    llm.complete_json(agent=, system=, user=, schema=, tier=) -> (dict, Usage)

- MockLLM      BM_LLM=mock (default). Returns the ACME fixtures. No key, no network.
- AnthropicLLM BM_LLM=live. Claude via the official `anthropic` SDK, structured JSON
               output (output_config.format), adaptive thinking, streaming.
- CachedLLM    wraps a live LLM with an on-disk cache keyed by the full prompt hash, so
               re-running an unchanged filing costs nothing (error K).

Models (override with env): BM_MODEL_ANALYST (default claude-opus-5) and
BM_MODEL_LIGHT (default claude-haiku-4-5). BM_EFFORT optionally sets
output_config.effort (low|medium|high|xhigh|max).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = ROOT / "fixtures" / "mock"
CACHE_DIR = ROOT / "orchestrator" / ".cache" / "llm"

# $ per 1M tokens (input, output) from the claude-api skill's cached table dated
# 2026-06-24. ASSUMPTION: prices may have changed; used only for run-cost estimates.
PRICES = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}
CACHE_READ_MULT, CACHE_WRITE_MULT = 0.1, 1.25


class LLMError(RuntimeError):
    """The model call failed, was refused, was truncated or returned unusable output."""


@dataclass
class Usage:
    model: str = ""
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    latency_s: float = 0.0
    cached_response: bool = False

    def add(self, other: "Usage") -> None:
        for f in ("calls", "input_tokens", "output_tokens", "cache_read_tokens",
                  "cache_write_tokens", "latency_s"):
            setattr(self, f, getattr(self, f) + getattr(other, f))
        self.model = self.model or other.model

    def cost_usd(self) -> float:
        price = PRICES.get(self.model)
        if not price:
            return 0.0
        inp, out = price
        return (self.input_tokens * inp + self.output_tokens * out
                + self.cache_read_tokens * inp * CACHE_READ_MULT
                + self.cache_write_tokens * inp * CACHE_WRITE_MULT) / 1_000_000


class LLM(Protocol):
    def complete_json(self, *, agent: str, system: str, user: str, schema: dict,
                      tier: str = "analyst") -> tuple[dict, Usage]: ...


def model_for(tier: str) -> str:
    if tier == "light":
        return os.environ.get("BM_MODEL_LIGHT", "claude-haiku-4-5")
    return os.environ.get("BM_MODEL_ANALYST", "claude-opus-5")


# --------------------------------------------------------------------------- mock
def _fx(name: str) -> dict:
    return json.loads((MOCK_DIR / name).read_text())


def _plain_scenario(s: dict) -> dict:
    return {
        "probability": s["probability"], "horizon_years": s["horizon_years"],
        "revenue_cagr": s["revenue_cagr"]["value"], "terminal_margin": s["terminal_margin"]["value"],
        "eps_at_horizon": s["eps_at_horizon"]["value"], "exit_multiple": s["exit_multiple"]["value"],
        "rationale": s["rationale"], "evidence": s["evidence"],
    }


def _wire_findings(analysis: dict, sections: list[str]) -> dict:
    """Mock analyses -> the LLM wire format (number_refs instead of value objects)."""
    out = {"summary": analysis["summary"], "findings": []}
    for i, f in enumerate(analysis["findings"]):
        out["findings"].append({
            "claim": f["claim"], "trend": f["trend"], "section": sections[min(i, len(sections) - 1)],
            "evidence": f["evidence"], "number_refs": f.get("_refs", []), "confidence": f["confidence"],
        })
    return out


_MOCK_REFS = {
    "forensic": [["metrics.margins.FY2025.gross"], [], ["metrics.per_share.dilution_yoy"]],
    "business": [[], [], []],
    "valuation": [["metrics.reverse_dcf.implied_fcf_cagr"]],
    "red_team": [["metrics.valuation.pe"], []],
}
_MOCK_SECTIONS = {
    "forensic": ["financial_quality", "financial_quality", "income_statement"],
    "business": ["competitive_position", "competitive_position", "management_guidance"],
    "valuation": ["valuation"],
    "red_team": ["risks", "risks"],
}


class MockLLM:
    """Deterministic stand-in that returns the frozen ACME fixtures (no network)."""

    def complete_json(self, *, agent: str, system: str, user: str, schema: dict,
                      tier: str = "analyst") -> tuple[dict, Usage]:
        u = Usage(model="mock", calls=1)
        if agent in ("forensic", "business", "red_team"):
            a = _fx(f"analysis_{agent}.json")
            for f, refs in zip(a["findings"], _MOCK_REFS[agent]):
                f["_refs"] = refs
            return _wire_findings(a, _MOCK_SECTIONS[agent]), u
        if agent == "balance_sheet":
            return {
                "summary": "FCF is strong and leverage is low, so buybacks are affordable, but the 2027 maturity needs watching.",
                "findings": [
                    {"claim": "Free cash flow of $600 million is well covered by operating cash flow and funds buybacks and debt service.",
                     "trend": "structurally_positive", "section": "free_cash_flow",
                     "evidence": [{"quote": "resulting in free cash flow of $600 million", "source_id": _mdna_id()}],
                     "number_refs": ["metrics.cash_flow.fcf", "metrics.cash_flow.fcf_yield"], "confidence": "high"},
                    {"claim": "Net debt is small relative to EBITDA, giving room to keep repurchasing shares.",
                     "trend": "structurally_positive", "section": "balance_sheet",
                     "evidence": [{"quote": "We repurchased 10 million shares during fiscal 2025 for an aggregate $450 million",
                                   "source_id": _mdna_id()}],
                     "number_refs": ["metrics.balance_sheet.net_debt", "metrics.balance_sheet.net_debt_to_ebitda"],
                     "confidence": "medium"},
                    {"claim": "A debt maturity in fiscal 2027 may need refinancing, though interest coverage is ample.",
                     "trend": "temporarily_negative", "section": "balance_sheet",
                     "evidence": [{"quote": "of which $400 million matures in fiscal 2027", "source_id": _risk_id()}],
                     "number_refs": ["metrics.balance_sheet.interest_coverage"], "confidence": "medium"},
                ]}, u
        if agent == "valuation":
            a = _fx("analysis_valuation.json")
            a["findings"][0]["_refs"] = _MOCK_REFS["valuation"][0]
            sc = _fx("scenarios.json")
            return {"analysis": _wire_findings(a, _MOCK_SECTIONS["valuation"]),
                    "scenarios": {k: _plain_scenario(v) for k, v in sc["scenarios"].items()},
                    "prior_shift": sc["prior_shift"]}, u
        if agent == "synthesizer":
            v = _fx("verdict.json")
            c = v["card"]
            return {
                "thesis": c["thesis"], "primary_catalyst": c["primary_catalyst"], "biggest_risk": c["biggest_risk"],
                "valuation": c["valuation"], "business_quality": c["business_quality"],
                "financial_strength": c["financial_strength"], "verdict": c["verdict"],
                "ten_thousand_dollar_answer": c["ten_thousand_dollar_answer"],
                "red_team_responses": v["red_team"]["responses_by_synthesizer"],
                "buyability_text": "The scores reflect a good business whose price already discounts a decade of double-digit growth.",
                "buy_more_if": ["Share price falls below $35 with guidance intact",
                                "Gross margin exceeds 41% for two consecutive quarters",
                                "Receivable days fall back below 49"],
                "sell_if": ["Gross margin falls below 38% for two consecutive quarters",
                            "Top-ten customer share rises above 35% of revenue",
                            "Fiscal 2027 debt is refinanced above 7% interest"],
                "committee_verdict_text": "Even with real switching costs, the base case trails the S&P 500, so we would rather hold the index.",
            }, u
        raise LLMError(f"MockLLM has no fixture for agent {agent!r}")


def _acc() -> str:
    return _fx("factsheet.json")["financials"][1]["accession"]


def _mdna_id() -> str:
    return f"src:edgar:{_acc()}:mdna"


def _risk_id() -> str:
    return f"src:edgar:{_acc()}:risk_factors"


# ------------------------------------------------------------------------- live
class AnthropicLLM:
    """Claude via the official SDK. Not exercised in CI (needs ANTHROPIC_API_KEY)."""

    def __init__(self, client=None, max_tokens: int = 16000):
        import anthropic  # imported lazily so mock mode needs no SDK
        self._anthropic = anthropic
        self.client = client or anthropic.Anthropic()
        self.max_tokens = max_tokens
        self.use_fallbacks = os.environ.get("BM_LLM_FALLBACKS", "1") != "0"

    def _params(self, model: str, system: str, user: str, schema: dict) -> dict:
        output_config: dict = {"format": {"type": "json_schema", "schema": schema}}
        if os.environ.get("BM_EFFORT"):
            output_config["effort"] = os.environ["BM_EFFORT"]
        return dict(
            model=model, max_tokens=self.max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            thinking={"type": "adaptive"}, output_config=output_config)

    def _stream(self, params: dict):
        if self.use_fallbacks:
            try:  # server-side refusal fallback (claude-api skill default for claude-opus-5)
                with self.client.beta.messages.stream(
                        betas=["server-side-fallback-2026-07-01"], fallbacks="default", **params) as s:
                    return s.get_final_message()
            except self._anthropic.BadRequestError as e:
                if not any(w in str(e).lower() for w in ("fallback", "beta")):
                    raise
                self.use_fallbacks = False  # this account/model rejects it: stop trying
        with self.client.messages.stream(**params) as s:
            return s.get_final_message()

    def complete_json(self, *, agent: str, system: str, user: str, schema: dict,
                      tier: str = "analyst") -> tuple[dict, Usage]:
        a = self._anthropic
        model = model_for(tier)
        t0 = time.monotonic()
        try:
            msg = self._stream(self._params(model, system, user, schema))
        except a.RateLimitError as e:
            raise LLMError(f"{agent}: rate limited: {e}") from e
        except a.APIConnectionError as e:
            raise LLMError(f"{agent}: network error: {e}") from e
        except a.APIStatusError as e:
            raise LLMError(f"{agent}: API error {e.status_code}: {e.message}") from e
        if msg.stop_reason == "refusal":
            raise LLMError(f"{agent}: model refused ({getattr(msg.stop_details, 'category', None)})")
        if msg.stop_reason == "max_tokens":
            raise LLMError(f"{agent}: output truncated at max_tokens")
        text = next((b.text for b in msg.content if b.type == "text"), None)
        if text is None:
            raise LLMError(f"{agent}: no text block in response")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"{agent}: response is not valid JSON: {e}") from e
        us = msg.usage
        return data, Usage(
            model=model, calls=1, input_tokens=us.input_tokens or 0, output_tokens=us.output_tokens or 0,
            cache_read_tokens=getattr(us, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(us, "cache_creation_input_tokens", 0) or 0,
            latency_s=time.monotonic() - t0)


class CachedLLM:
    """Disk cache in front of any LLM. Key = model + agent + full prompt + schema."""

    def __init__(self, inner: LLM, cache_dir: Path = CACHE_DIR):
        self.inner, self.dir = inner, Path(cache_dir)

    def complete_json(self, *, agent: str, system: str, user: str, schema: dict,
                      tier: str = "analyst") -> tuple[dict, Usage]:
        key = hashlib.sha256(json.dumps([model_for(tier), agent, system, user, schema],
                                        sort_keys=True).encode()).hexdigest()
        path = self.dir / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text()), Usage(model=model_for(tier), cached_response=True)
        data, usage = self.inner.complete_json(agent=agent, system=system, user=user, schema=schema, tier=tier)
        self.dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
        return data, usage


def get_llm() -> LLM:
    mode = os.environ.get("BM_LLM", "mock").lower()
    if mode == "mock":
        return MockLLM()
    if mode == "live":
        live: LLM = AnthropicLLM()
        return CachedLLM(live) if os.environ.get("BM_LLM_CACHE", "1") != "0" else live
    raise LLMError(f"BM_LLM must be 'mock' or 'live', got {mode!r}")
