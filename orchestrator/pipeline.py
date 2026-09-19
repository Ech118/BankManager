"""The analysis pipeline (plan.txt 15.14 P3 steps 1, 4-8).

check_scope -> build_factsheet -> compute_metrics -> scout -> analysts (parallel)
-> valuation -> evaluate_scenarios -> red team -> synthesizer -> audit -> verdict.

All numbers come from data.api / calc.api. Agents interpret; they never compute.
Every external module is injectable so tests can substitute fakes.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable

from agents import validate
from agents.llm import LLM, Usage, get_llm
from agents.refs import build_index
from agents.runner import ANALYSTS, ROSTER, SCHEMA_VERSION, AgentResult, Ctx, Doc, run_agent
from agents.sanitize import Flag, neutralize

from .render import render_sections

DISCLAIMER = ("This is AI-generated research for educational purposes only. It is not "
              "investment advice or a recommendation to buy or sell any security.")


class PipelineError(RuntimeError):
    pass


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_docs(fs: dict, get_text: Callable[[str], str], redact: Callable[[str], str] | None,
               max_chars: int) -> tuple[dict[str, Doc], list[Flag], list[str]]:
    """Pick the latest filing section per name, redact, neutralize injections, truncate."""
    filed = {p["accession"]: p["filed_date"] for p in fs["financials"]}
    entries = sorted(fs["filing_sections"], key=lambda s: filed.get(s["accession"], ""), reverse=True)
    docs: dict[str, Doc] = {}
    flags: list[Flag] = []
    gaps: list[str] = []
    for e in entries:
        if e["name"] in docs:
            continue
        try:
            text = get_text(e["source_id"])
        except Exception as ex:  # a missing section degrades quality but never blocks the run
            gaps.append(f"Filing section {e['name']} unavailable: {ex}")
            continue
        if redact:
            text = redact(text)
        text, f = neutralize(text, e["source_id"])
        flags += f
        if len(text) > max_chars:
            text = text[:max_chars] + "\n[TRUNCATED]"
        docs[e["name"]] = Doc(e["source_id"], e["name"], e["form"], e.get("period", ""), text)
    return docs, flags, gaps


def scout_analysis(fs: dict, ctx_docs: dict[str, Doc]) -> dict:
    dq = fs["data_quality"]
    peers = ", ".join(p["ticker"] for p in fs["peers"]) or "none"
    gaps = "; ".join(dq["gaps"]) or "none"
    summary = (f"{fs['company_name']} is in scope. Data quality: {dq['overall']} (gaps: {gaps}). "
               f"Peers: {peers}. Filing sections available: {', '.join(sorted(ctx_docs)) or 'none'}.")
    return {"schema_version": SCHEMA_VERSION, "agent": "scout", "ticker": fs["ticker"], "as_of": fs["as_of"],
            "model": "deterministic", "summary": summary, "findings": []}


def build_card(fs: dict, sr: dict, syn: dict) -> dict:
    """Numeric card fields come from code (fact sheet / calc), never from the LLM."""
    return {
        "company": fs["company_name"], "ticker": fs["ticker"],
        "price": fs["market"]["price"], "market_cap": fs["market"]["market_cap"],
        "thesis": syn["thesis"], "scores": sr["scores"],
        "p_beat_sp500_5y": sr["p_beat_sp500"]["5y"],
        "expected_5y_return": sr["expected_annualized_return"],
        "primary_catalyst": syn["primary_catalyst"], "biggest_risk": syn["biggest_risk"],
        "valuation": syn["valuation"], "business_quality": syn["business_quality"],
        "financial_strength": syn["financial_strength"], "verdict": syn["verdict"],
        "ten_thousand_dollar_answer": syn["ten_thousand_dollar_answer"],
    }


class Pipeline:
    def __init__(self, llm: LLM | None = None, data=None, calc=None, audit=None,
                 emit: Callable[..., None] | None = None, max_doc_chars: int = 60_000):
        if data is None:
            from data import api as data
        if calc is None:
            from calc import api as calc
        if audit is None:
            from audit import api as audit
        self.data, self.calc, self.audit = data, calc, audit
        self.llm = llm or get_llm()
        self._emit = emit or (lambda *a, **k: None)
        self.max_doc_chars = max_doc_chars
        self.stats: dict = {}

    # ------------------------------------------------------------------ helpers
    def _step(self, name: str, fn: Callable):
        self._emit(name, "started")
        t0 = time.monotonic()
        try:
            out = fn()
        except Exception as e:
            self._emit(name, "error", detail=str(e))
            raise
        self._emit(name, "done", seconds=round(time.monotonic() - t0, 2))
        return out

    def _agent(self, name: str, ctx: Ctx, feedback: list[str] | None = None) -> AgentResult:
        self._emit(name, "started")
        t0 = time.monotonic()
        try:
            res = run_agent(ROSTER[name], ctx, self.llm, emit=lambda s, **k: self._emit(name, s, **k),
                            feedback=feedback)
        except Exception as e:
            self._emit(name, "error", detail=str(e))
            raise
        res.usage.latency_s = res.usage.latency_s or (time.monotonic() - t0)
        self.stats["agents"][name] = {
            "model": res.usage.model, "calls": res.usage.calls, "attempts": res.attempts,
            "input_tokens": res.usage.input_tokens, "output_tokens": res.usage.output_tokens,
            "cache_read_tokens": res.usage.cache_read_tokens, "cache_write_tokens": res.usage.cache_write_tokens,
            "cost_usd": round(res.usage.cost_usd(), 4), "seconds": round(time.monotonic() - t0, 2),
            "dropped": res.dropped}
        self._emit(name, "done", seconds=round(time.monotonic() - t0, 2), dropped=len(res.dropped))
        return res

    # --------------------------------------------------------------------- run
    def run(self, ticker: str, as_of: str | None = None, redact: Callable[[str], str] | None = None) -> dict:
        t_start = time.monotonic()
        self.stats = {"ticker": ticker, "as_of": as_of, "started": _utc(), "agents": {}}
        scope = self._step("scope", lambda: self.data.check_scope(ticker))
        if not scope["in_scope"]:
            raise ValueError(scope["reason"])
        fs = self._step("data", lambda: self.data.build_factsheet(ticker, as_of))
        metrics = self._step("calc", lambda: self.calc.compute_metrics(fs))

        def get_text(sid: str) -> str:
            text = self.data.get_section_text(sid)
            return redact(text) if redact else text

        docs, flags, gaps = build_docs(fs, self.data.get_section_text, redact, self.max_doc_chars)
        for f in flags:
            self._emit("guard", "flagged", detail=f"possible prompt injection removed from {f.source_id}")
        ctx = Ctx(ticker=fs["ticker"], as_of=fs["as_of"], factsheet=fs, metrics=metrics,
                  index=build_index(fs, metrics), docs=docs)
        ctx.analyses["scout"] = self._step("scout", lambda: scout_analysis(fs, docs))

        with ThreadPoolExecutor(max_workers=len(ANALYSTS)) as pool:
            futures = {n: pool.submit(self._agent, n, ctx) for n in ANALYSTS}
            results = {n: f.result() for n, f in futures.items()}  # re-raises the first failure
        for n, r in results.items():
            ctx.analyses[n] = r.analysis

        val = self._agent("valuation", ctx)
        ctx.analyses["valuation"] = val.analysis
        sr = self._step("scenarios", lambda: self.calc.evaluate_scenarios(val.scenarios, fs, metrics))
        ctx.scenario_result = sr
        ctx.index = build_index(fs, metrics, sr)

        red = self._agent("red_team", ctx)
        ctx.analyses["red_team"] = red.analysis

        feedback: list[str] = []
        for attempt in (1, 2):
            syn_res = self._agent("synthesizer", ctx, feedback)
            card = build_card(fs, sr, syn_res.synthesis)
            cons = self.calc.validate_consistency(sr, card)
            if cons["ok"]:
                break
            feedback = [f"Consistency check failed: {i}" for i in cons["issues"]]
            self._emit("synthesizer", "retry", detail="; ".join(cons["issues"][:2]))
        else:
            raise PipelineError("verdict failed the consistency check twice: " + "; ".join(cons["issues"]))
        sr = {**sr, "consistency": cons}

        syn = syn_res.synthesis
        dq = {"overall": fs["data_quality"]["overall"], "gaps": list(fs["data_quality"]["gaps"]) + gaps
              + [f"Possible prompt-injection text removed from {f.source_id}: {f.snippet!r}" for f in flags]}
        if (flags or gaps) and dq["overall"] == "ok":
            dq["overall"] = "partial"
        verdict = {
            "schema_version": SCHEMA_VERSION, "ticker": fs["ticker"], "as_of": fs["as_of"],
            "generated_at": _utc(), "mode": fs["mode"], "disclaimer": DISCLAIMER, "card": card,
            "sections": render_sections(ctx.analyses, sr, val.scenarios, syn, card),
            "red_team": {"summary": red.analysis["summary"], "responses_by_synthesizer": syn["red_team_responses"]},
            "agent_outputs": dict(ctx.analyses), "scenario_result": sr,
            "audit": {"schema_version": SCHEMA_VERSION, "passed": False,
                      "issues": [{"severity": "warn", "path": "audit", "message": "audit pending"}]},
            "data_quality": dq,
        }
        verdict["audit"] = self._step("audit", lambda: self.audit.run_audit(
            fs, metrics, list(ctx.analyses.values()), verdict, get_text))
        try:
            validate.check(verdict, "verdict.json")
        except ValueError as e:
            raise PipelineError(str(e)) from e

        tot = Usage()
        for a in self.stats["agents"].values():
            tot.input_tokens += a["input_tokens"]; tot.output_tokens += a["output_tokens"]
        self.stats.update({
            "seconds": round(time.monotonic() - t_start, 2), "audit_passed": verdict["audit"]["passed"],
            "input_tokens": tot.input_tokens, "output_tokens": tot.output_tokens,
            "cost_usd_estimate": round(sum(a["cost_usd"] for a in self.stats["agents"].values()), 4),
            "injection_flags": len(flags), "verdict": card["verdict"]})
        return verdict
