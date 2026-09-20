"""Trailing-twelve-month inputs, when P1 publishes them.

A multiple divides today's price by a period of earnings, and which period that
is changes the answer. calc/ uses the latest FULL YEAR by default (CLAUDE.md:
flow metrics use the latest full year, never a trailing-quarter mix), but a data
provider quotes TTM, and mid-fiscal-year the two differ a lot: AAPL is 45.1x on
FY2025 EPS of $7.46 and about 36x on TTM EPS of roughly $9.38.

Both are defensible; disagreeing with every finance site without saying so is
not. So when a `<metric>_ttm` fact is present this module finds it, the flow
multiples use it, and `valuation.basis` names which period each multiple divided.

Three shapes are accepted, because P1 has not chosen one yet and any of them
would be reasonable:

1. `factsheet["ttm"]` - a block of `{metric: ValueObject}`, like a period with no
   label;
2. `<metric>_ttm` on the newest reported `FinancialPeriod`;
3. `<metric>_ttm` on any reported period (the newest wins).

Nothing here computes a TTM figure by summing quarters. That is P1's job: it
requires knowing which quarters are in the window and whether any was restated,
which is a data question, not a maths one. If no TTM fact exists, every flow
multiple falls back to the latest full year and says so.
"""

from __future__ import annotations

from calc.facts import Ledger
from calc.lineage import FactRef
from calc.value import add, sub

TTM_SUFFIX = "_ttm"

TTM_PERIOD_LABEL = "TTM"
"""What `valuation.basis` reports when a multiple used a trailing figure."""


def ttm_ref(ledger: Ledger, field: str) -> FactRef | None:
    """The TTM fact for one metric, or None. Newest period wins."""
    block = ledger.factsheet.get("ttm")
    if isinstance(block, dict):
        ref = _from_vo(ledger, block.get(field) or block.get(f"{field}{TTM_SUFFIX}"), field)
        if ref is not None:
            return ref
    for label in ledger.periods:
        ref = ledger.ref(label, f"{field}{TTM_SUFFIX}")
        if ref is not None:
            return ref._replace(metric=f"{field}{TTM_SUFFIX}")
    return None


def _from_vo(ledger: Ledger, vo: dict | None, field: str) -> FactRef | None:
    """A ref to a TTM value in `factsheet["ttm"]`, minting an id if P1 sent none.

    When P1 publishes these they will carry a fact_id in `derived_from`, like every
    other reported value on a real factsheet, and that id is cited unchanged. The
    minted fallback exists so a hand-built factsheet still produces resolvable
    lineage, and it lands in `input_facts` rather than being invented inline.
    """
    return ledger.mint(vo, f"{field}{TTM_SUFFIX}", f"ttm.{field}")


def flow_ref(ledger: Ledger, period: str, field: str) -> tuple[FactRef | None, str]:
    """The best flow input for a multiple, and which period it came from.

    Returns `(ref, "ttm")` when a trailing fact exists, else
    `(ref, "latest_full_year")`.
    """
    trailing = ttm_ref(ledger, field)
    if trailing is not None:
        return trailing, "ttm"
    return ledger.ref(period, field), "latest_full_year"


def derived_ttm(ledger: Ledger, metric: str, parts: dict[str, str], period: str) -> dict | None:
    """A TTM figure calc/ can build from other TTM facts: FCF and EBITDA.

    `parts` maps a formula variable to the metric name it needs in TTM form. All
    of them must be present, or there is no TTM figure and the caller falls back
    to the full year - a TTM numerator over a full-year input is exactly the mix
    the convention exists to prevent.
    """
    refs = {var: ttm_ref(ledger, field) for var, field in parts.items()}
    if any(ref is None for ref in refs.values()):
        return None
    values = {var: ref.value for var, ref in refs.items()}
    if metric == "fcf_ttm":
        total = sub(values["op_cash_flow"], values["capex"])
        formula = "op_cash_flow - capex"
    elif metric == "ebitda_ttm":
        total = add(values["operating_income"], values["depreciation_amortization"])
        formula = "operating_income + depreciation_amortization"
    else:
        raise ValueError(f"derived_ttm does not know how to build {metric}")
    return ledger.emit(
        total,
        metric=metric,
        period=period,
        unit="usd",
        formula=formula,
        inputs=refs,
        paths=[f"ttm.{field}" for field in parts.values()],
        reason="a trailing-twelve-month input is unavailable",
        derivation_extra={"window": "ttm"},
    )
