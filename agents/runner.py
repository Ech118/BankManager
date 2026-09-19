"""Agent definitions and the runner that turns one LLM call into a validated artifact.

For each agent: build prompt -> call LLM -> validate wire schema -> post-process
(drop findings without verbatim evidence, resolve number_refs to real value
objects, wrap scenario inputs) -> validate against schema/*.json. On a problem the
call is repeated ONCE with the problems listed; a second failure raises AgentError
(fail loudly, never ship unverified output).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from jsonschema import Draft202012Validator

from . import refs, schemas, validate
from .llm import LLM, Usage
from .promptkit import block, load_system

SCHEMA_VERSION = "1.0.0"
TOLERANCE_EPS = 0.15  # arithmetic guard on the valuation agent's own EPS


class AgentError(RuntimeError):
    pass


@dataclass(frozen=True)
class AgentSpec:
    name: str
    prompt: str
    doc_names: tuple[str, ...]
    sections: tuple[str, ...]
    kind: str            # "analysis" | "valuation" | "synthesis"
    tier: str = "analyst"


ROSTER: dict[str, AgentSpec] = {s.name: s for s in [
    AgentSpec("forensic", "forensic.md", ("mdna", "sbc_note", "segments_note"),
              ("financial_quality", "income_statement"), "analysis"),
    AgentSpec("business", "business.md", ("business", "risk_factors", "mdna"),
              ("management_guidance", "competitive_position", "catalysts"), "analysis"),
    AgentSpec("balance_sheet", "balance_sheet.md", ("mdna", "debt_note", "risk_factors"),
              ("balance_sheet", "free_cash_flow"), "analysis"),
    AgentSpec("valuation", "valuation.md", ("mdna", "business", "risk_factors"),
              ("valuation", "expectations_vs_reality"), "valuation"),
    AgentSpec("red_team", "red_team.md", ("risk_factors", "mdna", "business", "debt_note"),
              ("risks",), "analysis"),
    AgentSpec("synthesizer", "synthesizer.md", (), (), "synthesis"),
]}
ANALYSTS = ("forensic", "business", "balance_sheet")


@dataclass
class Doc:
    source_id: str
    name: str
    form: str
    period: str
    text: str          # exactly what the model sees (redacted + neutralized + truncated)


@dataclass
class Ctx:
    ticker: str
    as_of: str
    factsheet: dict
    metrics: dict
    index: dict
    docs: dict[str, Doc]
    analyses: dict[str, dict] = field(default_factory=dict)
    scenario_result: dict | None = None


@dataclass
class AgentResult:
    name: str
    analysis: dict | None = None
    scenarios: dict | None = None
    synthesis: dict | None = None
    dropped: list[dict] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    attempts: int = 0


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------- prompt building
def _analyst_digest(ctx: Ctx, names) -> str:
    out = []
    for n in names:
        a = ctx.analyses.get(n)
        if a:
            out.append({"agent": n, "summary": a["summary"], "findings": [
                {"claim": f["claim"], "trend": f["trend"], "confidence": f["confidence"]}
                for f in a["findings"]]})
    return json.dumps(out, indent=1)


def _calc_block(sr: dict) -> str:
    idx = refs.build_index({}, {}, sr)
    lines = [refs.format_table(idx, ("scenario_result",))]
    lines.append(f"scenario_result.p_beat_sp500 = {json.dumps(sr['p_beat_sp500'])}")
    lines.append(f"scenario_result.scores = {json.dumps(sr['scores'])}")
    lines.append(f"scenario_result.consistency = {json.dumps(sr['consistency'])}")
    return "\n".join(lines)


def build_user(spec: AgentSpec, ctx: Ctx, feedback: list[str]) -> str:
    parts = [f"TICKER: {ctx.ticker}\nAS OF: {ctx.as_of}\n"]
    if spec.kind != "synthesis":
        parts.append(block("DATA REFERENCE TABLE (untrusted data; cite paths in number_refs)",
                           refs.format_table(ctx.index)))
        allowed = ", ".join(spec.sections)
        parts.append(f"Allowed `section` values: {allowed}\n")
        docs = [ctx.docs[n] for n in spec.doc_names if n in ctx.docs]
        from .sanitize import wrap_document
        body = "\n\n".join(wrap_document(d.source_id, d.name, d.form, d.period, d.text) for d in docs)
        parts.append(block("DOCUMENTS (untrusted data; cite source_id + verbatim quote)",
                           body or "(no filing sections available: cite nothing and say the data is unavailable)"))
    if spec.name == "valuation":
        parts.append(block("UPSTREAM ANALYST FINDINGS (untrusted data)", _analyst_digest(ctx, ANALYSTS)))
    if spec.name == "red_team":
        parts.append(block("UPSTREAM ANALYST FINDINGS (untrusted data)",
                           _analyst_digest(ctx, (*ANALYSTS, "valuation"))))
        if ctx.scenario_result:
            parts.append(block("CALCULATION RESULTS", _calc_block(ctx.scenario_result)))
    if spec.name == "synthesizer":
        parts.append(block("ANALYST AND RED TEAM FINDINGS (untrusted data)",
                           _analyst_digest(ctx, (*ANALYSTS, "valuation", "red_team"))))
        parts.append(block("CALCULATION RESULTS (final; quote verbatim)", _calc_block(ctx.scenario_result or {})))
        parts.append(block("KEY FIGURES", refs.format_table(
            ctx.index, ("market.", "metrics.valuation", "metrics.cash_flow", "metrics.balance_sheet"))))
    if feedback:
        parts.append(block("PROBLEMS WITH YOUR PREVIOUS ATTEMPT (fix all of them)",
                           "\n".join(f"- {f}" for f in feedback)))
    return "\n".join(parts)


# ------------------------------------------------------------------ post-processing
def _verified_evidence(items: list[dict], ctx: Ctx, allowed: dict[str, Doc], dropped: list[dict], where: str):
    kept = []
    for ev in items or []:
        sid, quote = ev.get("source_id", ""), ev.get("quote", "")
        doc = allowed.get(sid)
        if doc is None:
            dropped.append({"where": where, "reason": f"evidence cites source not provided: {sid!r}"})
        elif len(norm(quote)) < 8:
            dropped.append({"where": where, "reason": "evidence quote too short"})
        elif norm(quote) not in norm(doc.text):
            dropped.append({"where": where, "reason": f"quote not verbatim in {sid}: {quote[:80]!r}"})
        else:
            kept.append({"quote": quote, "source_id": sid})
    return kept


def finalize_analysis(raw: dict, spec: AgentSpec, ctx: Ctx, model: str, dropped: list[dict]) -> dict:
    allowed = {ctx.docs[n].source_id: ctx.docs[n] for n in spec.doc_names if n in ctx.docs}
    findings = []
    for i, f in enumerate(raw.get("findings", [])):
        where = f"{spec.name}.findings[{i}]"
        evidence = _verified_evidence(f.get("evidence"), ctx, allowed, dropped, where)
        if not evidence:
            dropped.append({"where": where, "reason": "no verifiable evidence: finding dropped"})
            continue
        numbers, missing = refs.resolve(f.get("number_refs", []), ctx.index)
        for m in missing:
            dropped.append({"where": where, "reason": f"unknown number_ref {m!r} ignored"})
        section = f.get("section") if f.get("section") in spec.sections else spec.sections[0]
        findings.append({"claim": f["claim"], "trend": f["trend"], "evidence": evidence,
                         "numbers": numbers, "confidence": f["confidence"], "section": section})
    analysis = {"schema_version": SCHEMA_VERSION, "agent": spec.name, "ticker": ctx.ticker,
                "as_of": ctx.as_of, "model": model, "summary": raw["summary"], "findings": findings}
    validate.check(analysis, "analysis.json")
    return analysis


def _latest_annual(fs: dict) -> dict | None:
    return next((p for p in fs["financials"] if p["form"] == "10-K"), None)


def _vo(value, unit, type_, source_id=None, derived_from=None):
    out = {"value": value, "unit": unit, "type": type_, "status": "ok", "source_id": source_id}
    if derived_from:
        out["derived_from"] = derived_from
    return out


def finalize_scenarios(raw: dict, ctx: Ctx, dropped: list[dict]) -> tuple[dict, list[str]]:
    """Wrap the LLM's plain scenario inputs into scenarios.json; return (obj, problems)."""
    problems: list[str] = []
    sc = raw["scenarios"]
    total = sum(sc[k]["probability"] for k in ("bear", "base", "bull"))
    if abs(total - 1.0) > 0.02:
        problems.append(f"scenario probabilities sum to {total:.4f}; they must sum to 1.0")
    probs = {k: sc[k]["probability"] / total if total else 0 for k in sc}
    fs = ctx.factsheet
    base = _latest_annual(fs)
    shares = fs["market"]["shares_outstanding"]
    out = {}
    allowed = {d.source_id: d for d in ctx.docs.values()}
    for k in ("bear", "base", "bull"):
        s = sc[k]
        if base and base["revenue"]["status"] == "ok" and shares["status"] == "ok" and shares["value"]:
            implied = base["revenue"]["value"] * (1 + s["revenue_cagr"]) ** s["horizon_years"] \
                * s["terminal_margin"] / shares["value"]
            if implied > 0 and abs(s["eps_at_horizon"] - implied) / implied > TOLERANCE_EPS:
                problems.append(
                    f"{k}: eps_at_horizon {s['eps_at_horizon']:.4g} is inconsistent with your own drivers "
                    f"(revenue_cagr, terminal_margin, latest revenue and share count imply about {implied:.4g})")
        ev = _verified_evidence(s.get("evidence"), ctx, allowed, dropped, f"valuation.scenarios.{k}")
        out[k] = {
            "probability": round(probs[k], 6), "horizon_years": s["horizon_years"],
            "revenue_cagr": _vo(s["revenue_cagr"], "fraction", "assumption", "src:llm:valuation"),
            "terminal_margin": _vo(s["terminal_margin"], "fraction", "assumption", "src:llm:valuation"),
            "eps_at_horizon": _vo(s["eps_at_horizon"], "usd_per_share", "estimate", "src:llm:valuation"),
            "exit_multiple": _vo(s["exit_multiple"], "multiple", "assumption", "src:llm:valuation"),
            "rationale": s["rationale"], "evidence": ev}
    scenarios = {"schema_version": SCHEMA_VERSION, "ticker": ctx.ticker, "as_of": ctx.as_of,
                 "scenarios": out, "prior_shift": raw["prior_shift"]}
    if not problems:
        validate.check(scenarios, "scenarios.json")
    return scenarios, problems


# ------------------------------------------------------------------------- runner
def _wire_schema(spec: AgentSpec) -> dict:
    if spec.kind == "valuation":
        return schemas.valuation_out(list(spec.sections))
    if spec.kind == "synthesis":
        return schemas.SYNTHESIS_OUT
    return schemas.analysis_out(list(spec.sections))


def run_agent(spec: AgentSpec, ctx: Ctx, llm: LLM, emit=None, feedback: list[str] | None = None) -> AgentResult:
    system = load_system(spec.prompt)
    schema = _wire_schema(spec)
    wire = Draft202012Validator(schema)
    res = AgentResult(name=spec.name)
    feedback = list(feedback or [])
    for attempt in (1, 2):
        res.attempts = attempt
        raw, usage = llm.complete_json(agent=spec.name, system=system,
                                       user=build_user(spec, ctx, feedback), schema=schema, tier=spec.tier)
        res.usage.add(usage)
        problems = [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message[:160]}"
                    for e in wire.iter_errors(raw)]
        dropped: list[dict] = []
        if not problems:
            if spec.kind == "synthesis":
                res.synthesis = raw
            elif spec.kind == "valuation":
                analysis_raw = raw["analysis"]
                res.analysis = finalize_analysis(analysis_raw, spec, ctx, res.usage.model or usage.model, dropped)
                res.scenarios, sp = finalize_scenarios(raw, ctx, dropped)
                problems += sp
                if not res.analysis["findings"]:
                    problems.append("no finding survived evidence verification")
            else:
                res.analysis = finalize_analysis(raw, spec, ctx, res.usage.model or usage.model, dropped)
                if not res.analysis["findings"]:
                    problems.append("no finding survived evidence verification; quote exact text from the documents")
        res.dropped = dropped
        if not problems:
            return res
        if attempt == 2:
            raise AgentError(f"{spec.name}: invalid output after retry: " + "; ".join(problems[:5]))
        feedback = problems + [d["reason"] for d in dropped[:6]]
        if emit:
            emit("retry", detail="; ".join(problems[:3]))
    raise AgentError(f"{spec.name}: unreachable")
