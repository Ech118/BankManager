"""Claims for `scenarios` and `sp500_comparison`, generated from calc's ScenarioResult.

These two sections describe what CODE decided (weights, price targets, expected return vs the index),
so their claims are produced deterministically from the result and can never disagree with it. There
is no LLM here and no arithmetic: only reading a value, comparing its sign, and picking a sentence.

Each claim that carries a value cites a fact_id, because the Claim contract requires one for any
number (principle 2). The fact chosen is the newest annual diluted EPS: the scenarios are built on
EPS, so it is the honest anchor. Sentences contain no numerals; the figure is the claim's `value`.
"""

from __future__ import annotations

from schema.contracts.claims import Claim
from schema.contracts.enums import DerivedBy, Trend
from schema.contracts.scenario_result import ScenarioResult

CASES = ("bear", "base", "bull")


def anchor_fact_id(facts: list[dict]) -> str | None:
    """Newest annual eps_diluted fact (else any eps, else None)."""
    eps = [f for f in facts if f.get("metric") == "eps_diluted"]
    annual = [f for f in eps if str(f.get("fiscal_period", "")).startswith("FY")]
    pool = annual or eps
    return max(pool, key=lambda f: f["period_end"])["fact_id"] if pool else None


def build(sr: ScenarioResult, facts: list[dict]) -> dict[str, list[Claim]]:
    """{section_key: [claims]} for `scenarios` and `sp500_comparison`."""
    fid = anchor_fact_id(facts)
    cited = [fid] if fid else []
    clamped = sr.weights.any_clamped
    scenarios = [
        Claim(
            claim_id="claim:scenario:weights",
            text=(
                "One or more scenario weights proposed by the agent were outside the permitted band and were adjusted by code."
                if clamped
                else "The scenario weights proposed by the agent were within the permitted band and were used as proposed."
            ),
            derived_by=DerivedBy.CODE,
            trend=Trend.NEUTRAL,
        )
    ]
    for case in CASES:
        target = sr.scenarios[case].price_target
        scenarios.append(
            Claim(
                claim_id=f"claim:scenario:target-{case}",
                text=f"The {case} case price target is the value shown.",
                value=target if fid else None,
                fact_ids=cited if fid else [],
                derived_by=DerivedBy.CODE,
            )
        )
    excess = sr.expected_return_vs_sp500.long_term
    sign = excess.value if excess.status.value == "ok" else None
    verb = "matches" if sign is None or sign == 0 else ("exceeds" if sign > 0 else "trails")
    comparison = [
        Claim(
            claim_id="claim:scenario:excess",
            text=f"The probability-weighted expected return {verb} the assumed index return.",
            value=excess if fid else None,
            fact_ids=cited if fid else [],
            derived_by=DerivedBy.CODE,
            trend=Trend.NEUTRAL
            if verb == "matches"
            else (
                Trend.STRUCTURALLY_POSITIVE if verb == "exceeds" else Trend.STRUCTURALLY_NEGATIVE
            ),
        )
    ]
    return {"scenarios": scenarios, "sp500_comparison": comparison}
