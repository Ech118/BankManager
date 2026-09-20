"""Scenario evaluation and the weight-bounding algorithm.

Specified by docs/pipeline.md "Scenario weights" (amendment 1).

THE ALGORITHM, which must be implemented exactly as written because the mock
fixtures demonstrate it and the contract tests assert on it:

  1. Reject requested weights that do not sum to 1.0. A proposal that is not a
     distribution is a bug in the agent, not something to silently normalize.
  2. Clamp each weight into [default - band, default + band] from config.py.
  3. Redistribute the residual (1 - sum of clamped) across the UNCLAMPED weights
     in proportion to their size.
  4. Record one WeightClamp per scenario: requested, clamped_to, applied, plus
     `was_clamped` and `was_renormalized` flags.

Step 3 is the subtle one. Naive renormalization - scaling all three weights to
sum to 1 - would push a clamped weight straight back outside its band, undoing
step 2. Sending the residual only to the untouched weights keeps every applied
weight inside its own band.

Clamped, never rejected: an out-of-band request still contributes, it is just
bounded, and the record shows a reader exactly what the agent wanted.

eps_at_horizon (docs/requests/2026-09-20-p3-to-p2-step5-calc-contract.md): the
Scenario contract requires it, but it is arithmetic (revenue x growth x margin
/ shares), so no agent may supply it. This module derives it from
revenue_cagr, terminal_margin, the factsheet's latest annual revenue and
market.shares_outstanding - whatever the incoming Scenario carries in
eps_at_horizon is IGNORED, never trusted, so a stray agent-supplied number
cannot leak into the price target.
"""

from __future__ import annotations

from calc import config
from calc._util import num
from calc.lineage import assumption_value, derived_value
from calc.scenarios.prior import apply_shifts
from calc.scenarios.prior import p_beat_sp500 as compute_p_beat_sp500
from calc.scenarios.rubric import score_for_excess
from schema.contracts.enums import ScenarioName, ValueType
from schema.contracts.factsheet import Factsheet
from schema.contracts.metrics import Metrics
from schema.contracts.scenario_result import (
    Consistency,
    HorizonProbabilities,
    HorizonValues,
    ScenarioOut,
    ScenarioResult,
    ScenarioWeights,
    Scores,
    WeightClamp,
)
from schema.contracts.scenarios import PriorShift, Scenario, Scenarios

WEIGHT_TOLERANCE = 1e-9


def _clamp(value: float, default: float, band: float) -> float:
    lo, hi = default - band, default + band
    return min(hi, max(lo, value))


def bound_weights(requested: dict[str, float], reasons: dict[str, str] | None = None) -> ScenarioWeights:
    """Clamp, redistribute and record. The four-step algorithm above."""
    reasons = reasons or {}
    defaults = config.DEFAULT_SCENARIO_WEIGHTS
    band = config.SCENARIO_WEIGHT_BAND

    clamped = {name: _clamp(requested[name], defaults[name], band) for name in defaults}
    was_clamped = {name: abs(clamped[name] - requested[name]) > WEIGHT_TOLERANCE for name in defaults}

    residual = 1.0 - sum(clamped.values())
    free = {name: w for name, w in clamped.items() if not was_clamped[name]}
    applied = dict(clamped)
    if abs(residual) > 1e-12 and free:
        total_free = sum(free.values())
        for name, weight in free.items():
            applied[name] = weight + residual * (weight / total_free) if total_free else weight

    was_renormalized = {
        name: abs(applied[name] - clamped[name]) > WEIGHT_TOLERANCE for name in defaults
    }

    clamps = [
        WeightClamp(
            scenario=ScenarioName(name),
            requested=requested[name],
            clamped_to=clamped[name],
            applied=applied[name],
            default_weight=defaults[name],
            band=band,
            was_clamped=was_clamped[name],
            was_renormalized=was_renormalized[name],
            reason=reasons.get(name),
        )
        for name in ("bear", "base", "bull")
    ]
    return ScenarioWeights(
        bear=applied["bear"],
        base=applied["base"],
        bull=applied["bull"],
        clamps=clamps,
        any_clamped=any(was_clamped.values()),
        renormalized=any(was_renormalized.values()),
    )


def _implied_eps_at_horizon(factsheet: Factsheet, scenario: Scenario, name: str) -> float | None:
    """revenue x (1+g)^years x margin / shares - never trust the agent's own
    eps_at_horizon (it is arithmetic, plan.txt error C / ADR 0001)."""
    annual = factsheet.latest_annual_period
    period = factsheet.period(annual) if annual else None
    revenue = num(period.revenue) if period else None
    shares = num(factsheet.market.shares_outstanding)
    g = num(scenario.revenue_cagr)
    margin = num(scenario.terminal_margin)
    if None in (revenue, shares, g, margin) or shares == 0:
        return None
    return revenue * (1 + g) ** scenario.horizon_years * margin / shares


def price_target(scenario: dict, factsheet: Factsheet) -> float | None:
    """eps_at_horizon * exit_multiple."""
    eps = scenario.get("eps_at_horizon")
    exit_multiple = scenario.get("exit_multiple")
    if eps is None or exit_multiple is None:
        return None
    return eps * exit_multiple


def annualized_return(target: float | None, price: float | None, years: int) -> float | None:
    """(target / price) ** (1 / years) - 1."""
    if target is None or price is None or price <= 0 or not years:
        return None
    return (target / price) ** (1 / years) - 1


def evaluate_scenarios(
    scenarios: Scenarios,
    factsheet: Factsheet,
    metrics: Metrics,
    prior_shifts: list[PriorShift] | None = None,
) -> ScenarioResult:
    """The whole scenario computation.

    Expected value uses the APPLIED weights. `prior_shifts` collects every
    agent's requested tilt - the Scenario Agent's and the Red Team's - and
    prior.py caps their sum.

    Takes no `as_of`: the factsheet carries it (amendment 2).
    """
    requested = {name.value: s.probability for name, s in scenarios.scenarios.items()}
    reasons = {name.value: s.probability_rationale for name, s in scenarios.scenarios.items()}
    weights = bound_weights(requested, reasons)
    applied = {"bear": weights.bear, "base": weights.base, "bull": weights.bull}

    price = num(factsheet.market.price)
    scen_out: dict[ScenarioName, ScenarioOut] = {}
    expected_return = 0.0
    have_all_returns = True
    for name, scenario in scenarios.scenarios.items():
        eps = _implied_eps_at_horizon(factsheet, scenario, name.value)
        exit_multiple = num(scenario.exit_multiple)
        target = price_target({"eps_at_horizon": eps, "exit_multiple": exit_multiple}, factsheet)
        ann = annualized_return(target, price, scenario.horizon_years)
        weight = applied[name.value]
        if ann is None:
            have_all_returns = False
        else:
            expected_return += weight * ann

        target_vo = derived_value(
            target, "usd_per_share",
            [f"scenarios.{name.value}.eps_at_horizon", f"scenarios.{name.value}.exit_multiple"],
            type_=ValueType.ESTIMATE,
        )
        return_vo = derived_value(
            ann, "fraction",
            [f"scenario_result.scenarios.{name.value}.price_target", "market.price"],
            type_=ValueType.ESTIMATE,
        )
        scen_out[name] = ScenarioOut(
            probability=weight, price_target=target_vo, annualized_return=return_vo,
            eps_at_horizon=derived_value(
                eps, "usd_per_share",
                [f"scenarios.{name.value}.revenue_cagr", f"scenarios.{name.value}.terminal_margin",
                 "market.shares_outstanding"],
                type_=ValueType.ESTIMATE,
            ),
        )

    expected_value = expected_return if have_all_returns else None
    sp500_expected = config.SP500_EXPECTED_RETURN
    excess = None if expected_value is None else expected_value - sp500_expected

    shifts = prior_shifts if prior_shifts is not None else [scenarios.prior_shift]
    prior = apply_shifts(shifts)

    excess_vo = derived_value(
        excess, "fraction",
        ["scenario_result.expected_annualized_return", "scenario_result.sp500_expected_return"],
        type_=ValueType.ESTIMATE,
    )
    horizon_values = HorizonValues(short_term=excess_vo, medium_term=excess_vo, long_term=excess_vo)
    score = score_for_excess(excess)

    return ScenarioResult(
        schema_version=factsheet.schema_version,
        ticker=factsheet.ticker,
        as_of=factsheet.as_of,
        scenarios=scen_out,
        weights=weights,
        expected_annualized_return=derived_value(
            expected_value, "fraction",
            ["scenario_result.scenarios.*.annualized_return", "scenario_result.weights"],
            type_=ValueType.ESTIMATE,
        ),
        sp500_expected_return=assumption_value(sp500_expected, "fraction", "calc_assumptions"),
        expected_return_vs_sp500=horizon_values,
        excess_vs_sp500=horizon_values,
        p_beat_sp500=HorizonProbabilities(**compute_p_beat_sp500(prior)),
        prior=prior,
        scores=Scores(short_term=score, medium_term=score, long_term=score),
        consistency=Consistency(ok=True, issues=[]),
    )
