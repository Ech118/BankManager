"""Render a ResearchState into a Verdict. Pure, deterministic, no LLM.

Specified by docs/research-state.md and docs/adr/0004.

Rules:
  - Body markdown is built from a section's Claims, in order. Nothing is
    paraphrased or rewritten here.
  - Unverified claims are RENDERED AND MARKED, never dropped. A claim that
    quietly vanished would leave a reader unable to tell a checked report from
    an unchecked one. Claims the verifier has not seen are marked "unchecked".
  - Every number is formatted from its ValueObject, with its type
    (fact / estimate / assumption) carried through so the UI can colour it.
  - The disclaimer is non-negotiable and appears on every page (error M).
  - The verdict card is rendered FIRST, before any section.
  - Same state in, same report out: nothing here reads the clock or a random
    source (`generated_at` is the state's own `created_at`).

INPUTS beyond the state's contract fields (all in its `extra="allow"` space, set
by the Coordinator): `company_name`, `market` (a MarketSnapshot) and `synthesis`
(agents/synthesis.py). A report without them cannot produce a card, and says so
with ReportInputError instead of inventing values.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from agents.synthesis import Synthesis
from schema.contracts import SCHEMA_VERSION
from schema.contracts.common import DataQuality, Evidence
from schema.contracts.enums import VerificationStatus
from schema.contracts.market import MarketSnapshot
from schema.contracts.state import ResearchSection, ResearchState
from schema.contracts.verdict import RedTeamBlock, ReportSection, Verdict, VerdictCard

DISCLAIMER = (
    "This is AI-generated research for educational purposes only. It is not "
    "investment advice or a recommendation to buy or sell any security."
)
"""Rendered on every page. A test asserts its presence (error M)."""

TEMPLATES = Path(__file__).resolve().parent / "templates"
_MARKED = (VerificationStatus.FAILED, VerificationStatus.UNVERIFIED)


class ReportInputError(ValueError):
    """The state lacks something the report needs. Never papered over with a default."""


def _get(value: Any, key: str, default: Any = None) -> Any:
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


def format_value(value: Any) -> str:
    """Format one ValueObject for display.

    `unavailable` renders as "unavailable", never as 0 or a blank - the reader
    must be able to tell a missing number from a zero one.
    """
    if value is None or _get(value, "status") != "ok" or _get(value, "value") is None:
        return "unavailable"
    v, unit = float(_get(value, "value")), str(_get(value, "unit"))
    unit = getattr(_get(value, "unit"), "value", unit)
    if unit == "fraction":
        return f"{v * 100:.1f}%"
    if unit == "usd":
        a = abs(v)
        if a >= 1e9:
            return f"${v / 1e9:,.2f}B"
        if a >= 1e6:
            return f"${v / 1e6:,.1f}M"
        return f"${v:,.0f}"
    if unit == "usd_per_share":
        return f"${v:,.2f}"
    if unit == "multiple":
        return f"{v:.1f}x"
    if unit == "shares":
        return f"{v / 1e6:,.1f}M shares"
    if unit == "days":
        return f"{v:.0f} days"
    if unit == "count":
        return f"{v:,.0f}"
    return f"{v:.2f}"


def value_type(value: Any) -> str:
    t = _get(value, "type", "fact")
    return getattr(t, "value", str(t))


@lru_cache(maxsize=1)
def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["format_value"] = format_value
    env.filters["value_type"] = value_type
    return env


_BLOCK_START = re.compile(r"^(#{1,6} |> |---$|\| )")


def _tidy(md: str) -> str:
    """Deterministic whitespace normalisation: a blank line before headings, rules and
    blockquotes that follow ordinary text, and never more than one blank line."""
    out: list[str] = []
    for line in md.split("\n"):
        starts_block = bool(_BLOCK_START.match(line))
        prev = out[-1] if out else ""
        same_kind = (line.startswith("> ") and prev.startswith("> ")) or (
            line.startswith("|") and prev.startswith("|")
        )
        if starts_block and prev.strip() and not same_kind:
            out.append("")
        if line.strip() or (out and out[-1].strip()):
            out.append(line)
    return "\n".join(out).strip("\n")


def _claim_marker(status: VerificationStatus) -> str:
    if status in _MARKED:
        return "**[UNVERIFIED]**"
    if status is VerificationStatus.PENDING:
        return "_[unchecked]_"
    return ""


def _evidence(section: ResearchSection) -> list[Evidence]:
    seen: set[tuple[str, str]] = set()
    out: list[Evidence] = []
    for claim in section.claims:
        for ev in claim.evidence:
            key = (ev.source_id, " ".join(ev.quote.split()))
            if key not in seen:
                seen.add(key)
                out.append(ev)
    return out


def render_section(section: ResearchSection) -> ReportSection:
    """One section's markdown, built from its Claims.

    Unverified claims are included with a visible marker.
    """
    evidence = _evidence(section)
    body = (
        _env()
        .get_template("section.md")
        .render(section=section, evidence=evidence, marker=_claim_marker)
    )
    unverified = [c.claim_id for c in section.claims if c.verification_status in _MARKED]
    return ReportSection(
        id=section.section_key,
        title=section.title,
        body_markdown=_tidy(body),
        agent=section.owner,
        evidence=evidence,
        verification_status=section.verification_status,
        unverified_claim_ids=unverified,
    )


def _extra(state: ResearchState, key: str) -> Any:
    extra = state.model_extra or {}
    if key not in extra or extra[key] is None:
        raise ReportInputError(
            f"the ResearchState carries no `{key}`; the report cannot build its verdict card "
            f"without it (see agents/synthesis.py and docs/p3/STATUS.md)"
        )
    return extra[key]


def render_card(state: ResearchState) -> VerdictCard:
    """The verdict card. Every number comes from ScenarioResult or the market snapshot."""
    sr = state.scenario_result
    if sr is None:
        raise ReportInputError(
            "scenario_result is not set; calc.evaluate_scenarios must run before the report"
        )
    synth = Synthesis.model_validate(_extra(state, "synthesis"))
    market = MarketSnapshot.model_validate(_extra(state, "market"))
    return VerdictCard(
        company=str(_extra(state, "company_name")),
        ticker=state.ticker,
        price=market.price,
        market_cap=market.market_cap,
        thesis=synth.thesis,
        scores=sr.scores,
        p_beat_sp500_5y=sr.p_beat_sp500.long_term,
        expected_5y_return=sr.expected_annualized_return,
        expected_return_vs_sp500=sr.expected_return_vs_sp500,
        primary_catalyst=synth.primary_catalyst,
        biggest_risk=synth.biggest_risk,
        valuation=synth.valuation,
        business_quality=synth.business_quality,
        financial_strength=synth.financial_strength,
        verdict=synth.verdict,
        ten_thousand_dollar_answer=synth.ten_thousand_dollar_answer,
    )


def render(state: ResearchState) -> Verdict:
    """The whole report. A pure function of the state."""
    if state.verification is None:
        raise ReportInputError(
            "verification is not set; the verifier must run before the report (ADR 0005)"
        )
    synth = Synthesis.model_validate(_extra(state, "synthesis"))
    card = render_card(state)
    return Verdict(
        schema_version=SCHEMA_VERSION,
        ticker=state.ticker,
        as_of=state.as_of,
        generated_at=state.created_at,
        mode=state.mode,
        disclaimer=DISCLAIMER,
        card=card,
        sections=[render_section(s) for s in state.sections.as_list()],
        red_team=RedTeamBlock(**synth.red_team.model_dump()),
        agent_outputs=state.agent_outputs,
        scenario_result=state.scenario_result,
        audit=state.verification,
        data_quality=state.data_quality,
        metrics_ref=(state.model_extra or {}).get("metrics_ref"),
        state_version=state.state_version,
    )


def render_markdown(state: ResearchState, verdict: Verdict | None = None) -> str:
    """The report as one markdown document.

    With a Verdict: card first, then the case against, then the sections. Without
    one (a run that has not reached the synthesizer) it renders a PRELIMINARY report
    of the sections that exist, says so at the top, and shows no card: a verdict is
    never invented to fill the gap.
    """
    sections = (
        [render_section(s) for s in state.sections.as_list() if s.claims]
        if verdict is None
        else verdict.sections
    )
    quality: DataQuality = verdict.data_quality if verdict else state.data_quality
    md = (
        _env()
        .get_template("report.md")
        .render(
            verdict=verdict,
            card=verdict.card if verdict else None,
            red_team=verdict.red_team if verdict else None,
            scenario_result=verdict.scenario_result if verdict else None,
            audit=verdict.audit if verdict else state.verification,
            disclaimer=DISCLAIMER,
            state=state,
            ticker=state.ticker,
            as_of=state.as_of,
            data_quality=quality,
            sections=sections,
        )
    )
    return _tidy(md) + "\n"
