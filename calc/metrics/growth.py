"""Year-over-year growth and multi-year CAGR. Specified by docs/data-model.md.

Only emitted where a genuinely comparable prior period exists. Comparing a
quarter to a full year, or to a quarter of a different length, produces a number
that looks meaningful and is not, so the absence of a comparable prior yields no
entry rather than a plausible-looking one.

## The share-basis rule

A 10-K restates only the two comparative years it shows, so a five-year
per-share series can mix pre- and post-split values while every number in it is
correct as filed. NVDA's diluted share count rises 9.9x between FY2022 and
FY2023 for exactly that reason, and a naive EPS CAGR over that series is wrong by
a factor of ten (P1 -> P2, 2026-09-19).

So:

- **growth on totals is always computed** - revenue, net income, operating cash
  flow and FCF are untouched by a split;
- **per-share growth across a share-basis break** uses
  `eps_diluted_split_adjusted` / `shares_diluted_split_adjusted` when the
  factsheet carries them, and is otherwise **unavailable with the reason**. That
  is the case where nobody can produce an honest number.

The break is detected from the share count itself rather than from the filer
tagging a ratio, so an untagged split still stops the comparison.
"""

from __future__ import annotations

import re

from calc import config
from calc.facts import Ledger, missing_reason, nums, present
from calc.lineage import FactRef, var_name
from calc.value import cagr as _cagr
from calc.value import ratio_minus_one, sub

PER_SHARE_FIELDS = ("eps_diluted", "shares_diluted")
"""Fields whose comparability a split destroys."""

FCF_BANK_REASON = (
    "not applicable to a bank, insurer, broker or REIT: operating cash flow less "
    "capex does not describe this balance sheet"
)

SPLIT_REASON = (
    "per-share comparison spans a share-count discontinuity between {older} and "
    "{newer} (diluted shares change {ratio:.1f}x): the periods are reported on "
    "different share bases and no split-adjusted fact is on the factsheet"
)


def comparable_prior(ledger: Ledger, period: str) -> str | None:
    """The prior period of the same TYPE and length, or None.

    FY2025 -> FY2024, Q2-2026 -> Q2-2025. A quarter is never compared with a year.
    """
    label = _prior_label(period)
    return label if label in ledger.periods else None


def _prior_label(period: str) -> str | None:
    if period.startswith("FY"):
        try:
            return f"FY{int(period[2:]) - 1}"
        except ValueError:
            return None
    if "-" in period:
        quarter, year = period.split("-", 1)
        try:
            return f"{quarter}-{int(year) - 1}"
        except ValueError:
            return None
    return None


# --------------------------------------------------------------------------
# Share-basis breaks
# --------------------------------------------------------------------------
def share_basis_breaks(ledger: Ledger) -> dict[tuple[str, str], float]:
    """{(newer, older): ratio} for every annual boundary the share count jumps.

    Also honours a P1 `data_quality` gap that names the boundary in prose, so a
    break survives even if the counts themselves later look continuous.
    """
    breaks: dict[tuple[str, str], float] = {}
    annuals = ledger.annual_labels()
    for newer, older in zip(annuals, annuals[1:], strict=False):
        new_ref, old_ref = ledger.ref(newer, "shares_diluted"), ledger.ref(older, "shares_diluted")
        if not new_ref or not old_ref or not old_ref.value:
            continue
        ratio = new_ref.value / old_ref.value
        if ratio >= config.SHARE_BASIS_BREAK_RATIO or ratio <= 1 / config.SHARE_BASIS_BREAK_RATIO:
            breaks[(newer, older)] = ratio
    for gap in (ledger.factsheet.get("data_quality") or {}).get("gaps", []):
        text = gap.lower()
        if "share basis" not in text and "split" not in text:
            continue
        named = re.findall(r"FY\d{4}", gap)
        if len(named) >= 2:
            pair = (max(named[:2]), min(named[:2]))
            breaks.setdefault(pair, float("nan"))
    return breaks


def _breaks_between(ledger: Ledger, newer: str, older: str) -> list[tuple[tuple[str, str], float]]:
    """Every share-basis break that falls inside the window [older, newer]."""
    return [
        (pair, ratio)
        for pair, ratio in share_basis_breaks(ledger).items()
        if older <= pair[1] and pair[0] <= newer
    ]


def per_share_ref(ledger: Ledger, period: str, field: str) -> tuple[FactRef | None, bool]:
    """The best available per-share fact for a period: adjusted if P1 published one."""
    adjusted = ledger.ref(period, f"{field}_split_adjusted")
    if adjusted is not None:
        return adjusted, True
    return ledger.ref(period, field), False


def per_share_inputs(
    ledger: Ledger, field: str, newer: str, older: str
) -> tuple[dict[str, FactRef | None], str | None]:
    """Inputs for a per-share comparison, or a reason it cannot be made."""
    new_ref, new_adj = per_share_ref(ledger, newer, field)
    old_ref, old_adj = per_share_ref(ledger, older, field)
    found = _breaks_between(ledger, newer, older)
    if found and not (new_adj or old_adj):
        (break_new, break_old), ratio = found[0]
        return {}, SPLIT_REASON.format(
            older=break_old, newer=break_new, ratio=ratio if ratio == ratio else 0.0
        )
    return {
        var_name(field, newer, qualify=True): new_ref,
        var_name(field, older, qualify=True): old_ref,
    }, None


# --------------------------------------------------------------------------
# Year-over-year
# --------------------------------------------------------------------------
def growth_for(ledger: Ledger, period: str, prior: str, *, partial_scope: bool = False) -> dict:
    """Revenue, EPS, net income and FCF growth between two comparable periods."""
    out: dict[str, dict] = {}

    for key, metric, field in (
        ("revenue_yoy", "revenue_yoy", "revenue"),
        ("net_income_yoy", "net_income_yoy", "net_income"),
    ):
        inputs = {
            var_name(field, period, qualify=True): ledger.ref(period, field),
            var_name(field, prior, qualify=True): ledger.ref(prior, field),
        }
        values = list(nums(inputs).values())
        out[key] = ledger.emit(
            ratio_minus_one(values[0], values[1]),
            metric=metric,
            period=period,
            unit="fraction",
            formula=f"{list(inputs)[0]} / {list(inputs)[1]} - 1",
            inputs=present(inputs),
            paths=[f"financials.{period}.{field}", f"financials.{prior}.{field}"],
            reason=missing_reason(inputs, f"{prior} to {period}"),
        )

    inputs, blocked = per_share_inputs(ledger, "eps_diluted", period, prior)
    values = list(nums(inputs).values()) if inputs else [None, None]
    out["eps_yoy"] = ledger.emit(
        None if blocked else ratio_minus_one(values[0], values[1]),
        metric="eps_yoy",
        period=period,
        unit="fraction",
        formula=f"{list(inputs)[0]} / {list(inputs)[1]} - 1" if inputs else "eps / prior_eps - 1",
        inputs=present(inputs),
        paths=[f"financials.{period}.eps_diluted", f"financials.{prior}.eps_diluted"],
        reason=blocked or missing_reason(inputs, f"{prior} to {period}"),
    )

    inputs = {
        var_name("op_cash_flow", period, qualify=True): ledger.ref(period, "op_cash_flow"),
        var_name("capex", period, qualify=True): ledger.ref(period, "capex"),
        var_name("op_cash_flow", prior, qualify=True): ledger.ref(prior, "op_cash_flow"),
        var_name("capex", prior, qualify=True): ledger.ref(prior, "capex"),
    }
    names = list(inputs)
    values = nums(inputs)
    out["fcf_yoy"] = ledger.emit(
        None
        if partial_scope
        else ratio_minus_one(
            sub(values[names[0]], values[names[1]]), sub(values[names[2]], values[names[3]])
        ),
        metric="fcf_yoy",
        period=period,
        unit="fraction",
        formula=f"({names[0]} - {names[1]}) / ({names[2]} - {names[3]}) - 1",
        inputs=present(inputs),
        paths=[
            f"financials.{period}.op_cash_flow",
            f"financials.{period}.capex",
            f"financials.{prior}.op_cash_flow",
            f"financials.{prior}.capex",
        ],
        reason=FCF_BANK_REASON if partial_scope else missing_reason(inputs, f"{prior} to {period}"),
        not_applicable=partial_scope,
    )
    return out


def all_growth(ledger: Ledger, *, partial_scope: bool = False) -> dict[str, dict]:
    """Growth for every period that has a comparable prior."""
    out: dict[str, dict] = {}
    for label in ledger.periods:
        prior = comparable_prior(ledger, label)
        if prior:
            out[label] = growth_for(ledger, label, prior, partial_scope=partial_scope)
    return out


# --------------------------------------------------------------------------
# CAGR over the whole reported span
# --------------------------------------------------------------------------
def all_cagr(ledger: Ledger) -> dict:
    """Compound annual growth over the full span of reported full years.

    One entry per series, plus the window it was measured over, so a reader never
    has to guess whether a "CAGR" is three years or five.
    """
    annuals = ledger.annual_labels()
    if len(annuals) < 2:
        return {
            "years": 0,
            "from_period": None,
            "to_period": annuals[0] if annuals else None,
            "note": "a CAGR needs two full years; only one was reported",
        }
    newer, older = annuals[0], annuals[-1]
    years = len(annuals) - 1
    out: dict = {"years": years, "from_period": older, "to_period": newer}

    for key, field in (("revenue", "revenue"), ("net_income", "net_income")):
        inputs = {
            var_name(field, newer, qualify=True): ledger.ref(newer, field),
            var_name(field, older, qualify=True): ledger.ref(older, field),
        }
        names = list(inputs)
        values = nums(inputs)
        out[key] = ledger.emit(
            _cagr(values[names[0]], values[names[1]], years),
            metric=f"{field}_cagr",
            period=newer,
            unit="fraction",
            formula=f"({names[0]} / {names[1]}) ** (1 / {years}) - 1",
            inputs=present(inputs),
            paths=[f"financials.{newer}.{field}", f"financials.{older}.{field}"],
            reason=missing_reason(inputs, f"{older} to {newer}"),
        )

    inputs, blocked = per_share_inputs(ledger, "eps_diluted", newer, older)
    names = list(inputs)
    values = nums(inputs)
    out["eps_diluted"] = ledger.emit(
        None if blocked else _cagr(values[names[0]], values[names[1]], years) if inputs else None,
        metric="eps_diluted_cagr",
        period=newer,
        unit="fraction",
        formula=(
            f"({names[0]} / {names[1]}) ** (1 / {years}) - 1"
            if inputs
            else "(eps / oldest_eps) ** (1 / years) - 1"
        ),
        inputs=present(inputs),
        paths=[f"financials.{newer}.eps_diluted", f"financials.{older}.eps_diluted"],
        reason=blocked or missing_reason(inputs, f"{older} to {newer}"),
    )

    inputs = {
        var_name("op_cash_flow", newer, qualify=True): ledger.ref(newer, "op_cash_flow"),
        var_name("capex", newer, qualify=True): ledger.ref(newer, "capex"),
        var_name("op_cash_flow", older, qualify=True): ledger.ref(older, "op_cash_flow"),
        var_name("capex", older, qualify=True): ledger.ref(older, "capex"),
    }
    names = list(inputs)
    values = nums(inputs)
    out["fcf"] = ledger.emit(
        _cagr(
            sub(values[names[0]], values[names[1]]),
            sub(values[names[2]], values[names[3]]),
            years,
        ),
        metric="fcf_cagr",
        period=newer,
        unit="fraction",
        formula=f"(({names[0]} - {names[1]}) / ({names[2]} - {names[3]})) ** (1 / {years}) - 1",
        inputs=present(inputs),
        paths=[
            f"financials.{newer}.op_cash_flow",
            f"financials.{newer}.capex",
            f"financials.{older}.op_cash_flow",
            f"financials.{older}.capex",
        ],
        reason=missing_reason(inputs, f"{older} to {newer}"),
    )
    return out
