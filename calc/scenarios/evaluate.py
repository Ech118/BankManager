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

`eps_at_horizon` is derived HERE, not by an agent: it is
`revenue x (1 + cagr)^n x margin / shares`, which is arithmetic, and no agent does
arithmetic (ADR 0001, and the answer to P3's 2026-09-20 request). If a model
supplies a value anyway, calc/ recomputes and uses its own, recording the
disagreement.
"""

from __future__ import annotations

from calc import config
from calc.scenarios.prior import apply_shifts, p_beat_sp500
from calc.scenarios.rubric import derive_scores
from calc.value import div, value, vo_value
from schema.contracts.enums import HORIZON_YEARS, Horizon

SCENARIO_NAMES = ("bear", "base", "bull")
HORIZONS = tuple(h.value for h in Horizon)
HORIZON_TO_YEARS = {h.value: years for h, years in HORIZON_YEARS.items()}

EPS_INPUTS_MISSING = (
    "cannot derive eps_at_horizon: {missing} unavailable, so this scenario has no "
    "price target and is excluded from the expected value"
)


# --------------------------------------------------------------------------
# Step 1-4: the weights
# --------------------------------------------------------------------------
def bound_weights(requested: dict[str, float], rationales: dict[str, str] | None = None) -> dict:
    """Clamp, redistribute and record. The four-step algorithm above."""
    rationales = rationales or {}
    total = sum(requested.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"Scenario probabilities must sum to 1.0, got {total}")

    band = config.SCENARIO_WEIGHT_BAND
    defaults = config.DEFAULT_SCENARIO_WEIGHTS
    clamped: dict[str, float] = {}
    was_clamped: dict[str, bool] = {}
    for name in SCENARIO_NAMES:
        want = float(requested[name])
        low, high = defaults[name] - band, defaults[name] + band
        clamped[name] = max(low, min(high, want))
        was_clamped[name] = abs(clamped[name] - want) > 1e-12

    # Step 3: the residual goes ONLY to the weights the band did not touch, in
    # proportion to their size. Scaling all three would push a clamped weight
    # straight back out of its band and undo step 2.
    applied = _redistribute(clamped, was_clamped, defaults, band)

    clamps = [
        {
            "scenario": name,
            "requested": round(float(requested[name]), 10),
            "clamped_to": round(clamped[name], 10),
            "applied": round(applied[name], 10),
            "default_weight": defaults[name],
            "band": band,
            "was_clamped": was_clamped[name],
            "was_renormalized": abs(applied[name] - clamped[name]) > 1e-9,
            "reason": rationales.get(name) or None,
        }
        for name in SCENARIO_NAMES
    ]
    return {
        "bear": round(applied["bear"], 10),
        "base": round(applied["base"], 10),
        "bull": round(applied["bull"], 10),
        "clamps": clamps,
        "any_clamped": any(clamp["was_clamped"] for clamp in clamps),
        "renormalized": any(clamp["was_renormalized"] for clamp in clamps),
    }


def _redistribute(
    clamped: dict[str, float],
    was_clamped: dict[str, bool],
    defaults: dict[str, float],
    band: float,
) -> dict[str, float]:
    """Push the residual onto the weights that can absorb it, in proportion.

    The documented rule first: the residual goes to the weights the band did NOT
    touch, in proportion to their size, so no clamped weight is pushed back out.

    Then the degenerate case the rule does not cover. If ALL THREE weights were
    clamped - an agent asking for bear 0, base 1, bull 0 - there is no untouched
    weight to give the residual to, and stopping there would return 0.85 instead of
    a distribution. So the leftover is spread across whichever weights still have
    HEADROOM IN THE DIRECTION IT NEEDS, proportionally, clipping each to its band,
    and repeated until it is absorbed. It always can be: the bands sum to
    [0.55, 1.45] and 1.0 sits inside that.
    """
    applied = dict(clamped)
    order = [name for name in SCENARIO_NAMES if not was_clamped[name]]
    for names in (order, list(SCENARIO_NAMES)):
        for _ in range(len(SCENARIO_NAMES) + 1):
            residual = 1.0 - sum(applied.values())
            if abs(residual) <= 1e-12 or not names:
                break
            room = {
                name: (
                    defaults[name] + band - applied[name]
                    if residual > 0
                    else applied[name] - (defaults[name] - band)
                )
                for name in names
            }
            movable = [name for name in names if room[name] > 1e-12]
            if not movable:
                break
            share_total = sum(applied[name] for name in movable)
            for name in movable:
                share = applied[name] / share_total if share_total > 0 else 1.0 / len(movable)
                step = residual * share
                step = min(step, room[name]) if residual > 0 else max(step, -room[name])
                applied[name] += step
    return applied


# --------------------------------------------------------------------------
# One scenario
# --------------------------------------------------------------------------
def eps_at_horizon(scenario: dict, factsheet: dict, metrics: dict) -> dict:
    """revenue x (1 + revenue_cagr)^n x terminal_margin / shares_outstanding.

    Derived here rather than supplied, because it is arithmetic. The share count
    is today's (`market.shares_outstanding`): buybacks and dilution over five
    years are not forecastable from a factsheet, and the exit multiple is where a
    reader's judgement about them belongs.
    """
    period = metrics.get("latest_annual_period")
    reported = _period(factsheet, period)
    revenue = vo_value((reported or {}).get("revenue"))
    cagr = vo_value(scenario.get("revenue_cagr"))
    margin = vo_value(scenario.get("terminal_margin"))
    shares = vo_value((factsheet.get("market") or {}).get("shares_outstanding"))
    years = scenario.get("horizon_years")

    paths = [
        f"scenarios.{scenario.get('_name', 'case')}.revenue_cagr",
        f"scenarios.{scenario.get('_name', 'case')}.terminal_margin",
        "market.shares_outstanding",
        f"financials.{period}.revenue",
    ]
    missing = [
        name
        for name, val in (
            ("revenue", revenue),
            ("revenue_cagr", cagr),
            ("terminal_margin", margin),
            ("market.shares_outstanding", shares),
            ("horizon_years", years),
        )
        if val is None
    ]
    if missing:
        return value(
            None,
            "usd_per_share",
            "estimate",
            derived_from=paths,
            reason=EPS_INPUTS_MISSING.format(missing=", ".join(missing)),
        )

    eps = div(revenue * (1 + cagr) ** years * margin, shares)
    out = value(eps, "usd_per_share", "estimate", derived_from=paths)
    out["formula"] = (
        f"revenue[{period}] * (1 + revenue_cagr) ** {years} * terminal_margin "
        "/ market.shares_outstanding"
    )
    supplied = vo_value(scenario.get("eps_at_horizon"))
    if supplied is not None:
        out["agent_supplied"] = supplied
        if eps is None or abs(supplied - eps) > max(1e-6, abs(eps) * 1e-6):
            out["note"] = (
                f"an agent supplied {supplied:.4f}; calc/ recomputed "
                f"{eps:.4f} from the inputs and uses its own (ADR 0001)"
            )
    return out


def price_target(scenario: dict, eps: dict) -> dict:
    """eps_at_horizon * exit_multiple."""
    multiple = vo_value(scenario.get("exit_multiple"))
    eps_value = vo_value(eps)
    name = scenario.get("_name", "case")
    paths = [f"scenarios.{name}.eps_at_horizon", f"scenarios.{name}.exit_multiple"]
    if eps_value is None or multiple is None:
        return value(
            None,
            "usd_per_share",
            "estimate",
            derived_from=paths,
            reason=(
                eps.get("unavailable_reason")
                if eps_value is None
                else "exit_multiple unavailable, so there is no price target"
            ),
        )
    return value(eps_value * multiple, "usd_per_share", "estimate", derived_from=paths)


def annualized_return(
    target: float | None, price: float | None, years: float | None
) -> float | None:
    """(target / price) ** (1 / years) - 1."""
    if target is None or price is None or not years or price <= 0 or target <= 0:
        return None
    return (target / price) ** (1.0 / years) - 1


def horizon_breakdown(
    name: str, annual_return: float | None, price: float | None, years: float | None
) -> dict:
    """Value per share, cumulative return and annualized return at each horizon.

    The scenario gives one terminal price at its own horizon, which implies one
    constant annual rate. Interpolating that path is the only defensible way to
    answer "what about three years?" without more inputs - so the ANNUALIZED
    figure is the same at every horizon by construction, and the CUMULATIVE one is
    the number that differs. A bear case at -14%/yr reads mildly; -52% over five
    years does not, and the reader deserves the second framing.
    """
    out: dict = {}
    for horizon in HORIZONS:
        span = HORIZON_TO_YEARS[horizon]
        if annual_return is None or price is None:
            out[horizon] = {
                "value_per_share": value(
                    None,
                    "usd_per_share",
                    "estimate",
                    reason="this scenario has no annualized return",
                ),
                "cumulative_return": value(
                    None, "fraction", "estimate", reason="this scenario has no annualized return"
                ),
                "annualized_return": value(
                    None, "fraction", "estimate", reason="this scenario has no annualized return"
                ),
            }
            continue
        level = price * (1 + annual_return) ** span
        out[horizon] = {
            "value_per_share": value(
                level,
                "usd_per_share",
                "estimate",
                derived_from=[
                    f"scenario_result.scenarios.{name}.annualized_return",
                    "market.price",
                ],
            ),
            "cumulative_return": value(
                (1 + annual_return) ** span - 1,
                "fraction",
                "estimate",
                derived_from=[f"scenario_result.scenarios.{name}.annualized_return"],
            ),
            "annualized_return": value(
                annual_return,
                "fraction",
                "estimate",
                derived_from=[f"scenario_result.scenarios.{name}.annualized_return"],
            ),
            "years": span,
        }
        if years and span > years:
            out[horizon]["extrapolated"] = True
            out[horizon]["note"] = (
                f"the scenario's own horizon is {years:g} years; {span:g} years assumes the "
                "same rate continues"
            )
    return out


# --------------------------------------------------------------------------
# The index
# --------------------------------------------------------------------------
def sp500_expected_return(factsheet: dict) -> dict:
    """The index return every verdict is measured against.

    Prefers `sp500_baseline.expected_return` if a factsheet ever carries one;
    otherwise `config.SP500_EXPECTED_RETURN`. Either way the factsheet's own
    baseline (forward P/E, earnings yield, risk-free rate) is echoed beside it, so
    a reader can see what the assumption is being checked against.
    """
    baseline = factsheet.get("sp500_baseline") or {}
    published = vo_value(baseline.get("expected_return"))
    if published is not None:
        out = value(
            published,
            "fraction",
            "assumption",
            source_id=(baseline.get("expected_return") or {}).get("source_id")
            or f"src:config:{config.CONFIG_SOURCE}",
        )
        out["basis"] = "factsheet"
    else:
        out = value(
            config.SP500_EXPECTED_RETURN,
            "fraction",
            "assumption",
            source_id=f"src:config:{config.CONFIG_SOURCE}",
        )
        out["basis"] = "config"
    out["baseline"] = {
        key: baseline.get(key)
        for key in ("forward_pe", "earnings_yield", "risk_free_rate", "as_of")
        if baseline.get(key) is not None
    }
    return out


# --------------------------------------------------------------------------
# Sensitivity
# --------------------------------------------------------------------------
def bear_weight_that_flips(returns: dict[str, float | None], weights: dict, target: float) -> dict:
    """The bear weight at which the expected return crosses the index.

    The other two weights keep their current ratio to each other, so the question
    is one-dimensional:

        E(x) = x * r_bear + (1 - x) * r_rest,  r_rest = the base/bull blend

    and E(x) = target solves in closed form. Reporting `reachable: false` matters
    as much as the number: for ACME the flip point is a NEGATIVE bear weight,
    which says the verdict does not depend on the bear case at all.
    """
    bear = returns.get("bear")
    others = [(name, returns.get(name), weights[name]) for name in ("base", "bull")]
    usable = [(name, ret, weight) for name, ret, weight in others if ret is not None]
    weight_total = sum(weight for _, _, weight in usable)
    if bear is None or not usable or weight_total <= 0:
        return {
            "flips_at_bear_probability": None,
            "reachable": False,
            "reason": "a scenario return is unavailable, so there is nothing to solve",
        }
    rest = sum(ret * weight for _, ret, weight in usable) / weight_total
    if abs(bear - rest) < 1e-12:
        return {
            "flips_at_bear_probability": None,
            "reachable": False,
            "reason": "every scenario returns the same, so the weight cannot change the verdict",
        }
    flip = (target - rest) / (bear - rest)
    band = config.SCENARIO_WEIGHT_BAND
    low = round(config.DEFAULT_SCENARIO_WEIGHTS["bear"] - band, 10)
    high = round(config.DEFAULT_SCENARIO_WEIGHTS["bear"] + band, 10)
    out = {
        "flips_at_bear_probability": round(flip, 10),
        "current_bear_probability": weights["bear"],
        "allowed_band": [low, high],
        "reachable": 0.0 <= flip <= 1.0,
        "inside_allowed_band": low - 1e-9 <= flip <= high + 1e-9,
        "target": target,
        "bear_return": bear,
        "base_bull_blend": round(rest, 10),
    }
    if not out["reachable"]:
        direction = "lowering" if flip < 0 else "raising"
        out["reason"] = (
            f"no bear weight in [0, 1] flips the verdict: {direction} it past the "
            f"limit would be needed. With the bear case at "
            f"{'0' if flip < 0 else '100'}% the expected return is "
            f"{(rest if flip < 0 else bear):.1%}/yr against the index's {target:.1%}/yr."
        )
    elif not out["inside_allowed_band"]:
        out["reason"] = (
            f"the verdict flips at a bear weight of {flip:.0%}, outside the band "
            f"[{low:.0%}, {high:.0%}] the Scenario Agent may ask for"
        )
    else:
        out["reason"] = (
            f"the verdict flips at a bear weight of {flip:.0%}, against the "
            f"{weights['bear']:.0%} applied"
        )
    return out


# --------------------------------------------------------------------------
# The whole computation
# --------------------------------------------------------------------------
def evaluate_scenarios(
    scenarios: dict,
    factsheet: dict,
    metrics: dict,
    prior_shifts: list[dict] | None = None,
) -> dict:
    """The whole scenario computation.

    Expected value uses the APPLIED weights. `prior_shifts` collects every
    agent's requested tilt - the Scenario Agent's and the Red Team's - and
    prior.py caps their sum.

    Takes no `as_of`: the factsheet carries it (amendment 2).
    """
    cases = scenarios["scenarios"]
    requested = {name: cases[name]["probability"] for name in SCENARIO_NAMES}
    rationales = {name: cases[name].get("probability_rationale") or None for name in SCENARIO_NAMES}
    weights = bound_weights(requested, rationales)

    price = vo_value((factsheet.get("market") or {}).get("price"))
    index = sp500_expected_return(factsheet)
    target = index["value"]

    out_scenarios: dict = {}
    returns: dict[str, float | None] = {}
    excluded: list[str] = []
    for name in SCENARIO_NAMES:
        case = {**cases[name], "_name": name}
        years = case.get("horizon_years")
        eps = eps_at_horizon(case, factsheet, metrics)
        target_price = price_target(case, eps)
        annual = annualized_return(vo_value(target_price), price, years)
        returns[name] = annual
        out_scenarios[name] = {
            "probability": weights[name],
            "price_target": target_price,
            "annualized_return": value(
                annual,
                "fraction",
                "estimate",
                derived_from=[f"scenario_result.scenarios.{name}.price_target", "market.price"],
                reason=(
                    target_price.get("unavailable_reason")
                    or "no market price to compare the target against"
                ),
            ),
            "eps_at_horizon": eps,
            "horizon_years": years,
            "by_horizon": horizon_breakdown(name, annual, price, years),
        }
        if annual is None:
            excluded.append(
                f"{name}: {out_scenarios[name]['annualized_return'].get('unavailable_reason')}"
            )

    # Expected value over the scenarios that HAVE a return, with the excluded ones
    # named. A scenario silently dropped from an expected value is a wrong number;
    # one excluded with a reason is a smaller sample a reader can see.
    usable = {name: ret for name, ret in returns.items() if ret is not None}
    weight_total = sum(weights[name] for name in usable)
    expected = (
        sum(returns[name] * weights[name] for name in usable) / weight_total
        if usable and weight_total > 0
        else None
    )
    if usable and weight_total > 0 and abs(weight_total - 1.0) > 1e-9:
        excluded.append(
            f"the expected value was renormalized over {weight_total:.0%} of the weight, "
            "because the excluded scenarios have no return"
        )

    expected_vo = value(
        expected,
        "fraction",
        "estimate",
        derived_from=["scenario_result.scenarios.*.annualized_return", "scenario_result.weights"],
        reason="no scenario produced an annualized return, so there is no expected value",
    )
    excess = None if expected is None else expected - target
    per_horizon = {
        horizon: value(
            excess,
            "fraction",
            "estimate",
            derived_from=[
                "scenario_result.expected_annualized_return",
                "scenario_result.sp500_expected_return",
            ],
            reason=expected_vo.get("unavailable_reason"),
        )
        for horizon in HORIZONS
    }

    prior = apply_shifts(_collect_shifts(scenarios, prior_shifts))
    result = {
        "schema_version": scenarios.get("schema_version") or factsheet["schema_version"],
        "ticker": factsheet["ticker"],
        "as_of": factsheet["as_of"],
        "scenarios": out_scenarios,
        "weights": weights,
        "expected_annualized_return": expected_vo,
        "sp500_expected_return": index,
        "expected_return_vs_sp500": per_horizon,
        "excess_vs_sp500": {horizon: dict(vo) for horizon, vo in per_horizon.items()},
        "p_beat_sp500": p_beat_sp500(prior),
        "prior": prior,
        "sensitivity": bear_weight_that_flips(returns, weights, target),
        "consistency": {"ok": True, "issues": []},
    }
    if excluded:
        result["excluded_scenarios"] = excluded
    result["scores"] = derive_scores(result)
    return result


def _collect_shifts(scenarios: dict, prior_shifts: list[dict] | None) -> list[dict]:
    """The shifts to sum. An explicit list is authoritative.

    When P3 passes `prior_shifts` it already contains the Scenario Agent's own
    shift, so using `scenarios["prior_shift"]` as well would count it twice.
    """
    if prior_shifts:
        return list(prior_shifts)
    embedded = scenarios.get("prior_shift")
    return [embedded] if embedded else []


def _period(factsheet: dict, label: str | None) -> dict | None:
    for period in factsheet.get("financials") or []:
        if period["period"] == label:
            return period
    return None
