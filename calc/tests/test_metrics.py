"""compute_metrics: the pinned ACME numbers, and what the real filers break.

Four things are being protected here:

1. **the pinned numbers** - every ValueObject in fixtures/mock/metrics.json is
   what calc/ computes from fixtures/mock/factsheet.json, to the last digit;
2. **lineage** - every derived fact recomputes from its inputs and is filed on
   the date of its LAST input;
3. **missing data** - an absent input yields unavailable WITH A REASON, never 0;
4. **the real recordings** - a bank, a stock split and an untagged interest
   expense all run without an exception and without a wrong number.
"""

from __future__ import annotations

import pytest

from calc.api import compute_metrics
from calc.facts import is_partial_scope
from calc.lineage import latest_filed_at, recompute
from calc.tests.support import load_real
from schema.contracts.facts import FinancialFact
from schema.contracts.metrics import Metrics


# --------------------------------------------------------------------------
# 1. The pinned ACME numbers
# --------------------------------------------------------------------------
def _leaves(obj, path=""):
    """Every ValueObject value in a Metrics object, by dotted path."""
    if isinstance(obj, dict):
        if "status" in obj and "unit" in obj:
            yield path, obj.get("value")
            return
        for key, val in obj.items():
            yield from _leaves(val, f"{path}.{key}" if path else key)
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            yield from _leaves(val, f"{path}.{i}")


def test_fy2025_fcf_is_600m(acme):
    """The one number the roadmap pins by hand: 850M operating cash less 250M capex."""
    assert compute_metrics(acme)["cash_flow"]["fcf"]["value"] == 600_000_000


def test_every_pinned_value_object_matches(acme, pinned_metrics):
    got = dict(_leaves(compute_metrics(acme)))
    mismatched = {}
    for path, want in _leaves(pinned_metrics):
        if path.startswith("quality_flags"):
            continue  # covered separately: one flag needs data the factsheet lacks
        assert path in got, f"{path} is missing from compute_metrics output"
        if isinstance(want, (int, float)) and isinstance(got[path], (int, float)):
            if abs(want - got[path]) > max(1e-9, abs(want) * 1e-9):
                mismatched[path] = (want, got[path])
        elif want != got[path]:
            mismatched[path] = (want, got[path])
    assert not mismatched, f"pinned values changed: {mismatched}"


def test_margins_and_growth_are_fractions(acme):
    metrics = compute_metrics(acme)
    assert metrics["margins"]["FY2025"]["gross"]["value"] == pytest.approx(0.40)
    assert metrics["margins"]["FY2025"]["fcf"]["value"] == pytest.approx(0.12)
    assert metrics["growth"]["FY2025"]["revenue_yoy"]["value"] == pytest.approx(0.1111111111)
    assert metrics["growth"]["FY2025"]["net_income_yoy"]["value"] == pytest.approx(
        592_000_000 / 488_000_000 - 1
    )
    assert metrics["per_share"]["dilution_yoy"]["value"] < 0, "ACME bought stock back"


def test_cagr_uses_the_whole_reported_span(acme):
    cagr = compute_metrics(acme)["cagr"]
    assert (cagr["from_period"], cagr["to_period"], cagr["years"]) == ("FY2023", "FY2025", 2)
    assert cagr["revenue"]["value"] == pytest.approx((5e9 / 4.1e9) ** 0.5 - 1)
    assert cagr["fcf"]["value"] == pytest.approx((600e6 / 400e6) ** 0.5 - 1)


def test_net_debt_and_valuation(acme):
    metrics = compute_metrics(acme)
    assert metrics["balance_sheet"]["net_debt"]["value"] == 150_000_000
    assert metrics["valuation"]["pe"]["value"] == pytest.approx(50 / 1.48)
    assert metrics["valuation"]["primary_multiple"] == "pe"


def test_metrics_validate_against_the_contract(acme):
    Metrics.model_validate(compute_metrics(acme))


def test_dso_flag_fires_on_acme(acme):
    flags = {f["flag"]: f for f in compute_metrics(acme)["quality_flags"]}
    assert flags["dso_rising"]["severity"] == "low"
    assert "48.7 to 51.1 days" in flags["dso_rising"]["detail"]
    assert flags["buyback_flatters_eps"]["severity"] == "low"


# --------------------------------------------------------------------------
# 2. Lineage: derived facts, filed_at, recompute
# --------------------------------------------------------------------------
def _resolver(metrics, factsheet):
    """fact_id -> value, over the factsheet's reported facts and calc/'s own."""
    table: dict[str, float] = {}
    for period in factsheet["financials"]:
        for field, vo in period.items():
            if isinstance(vo, dict) and vo.get("status") == "ok":
                for fid in vo.get("derived_from") or []:
                    if isinstance(fid, str) and fid.startswith("fact:"):
                        table[fid] = vo["value"]
                table.setdefault(
                    f"fact:{factsheet['ticker']}:{field}:{period['period']}", vo.get("value")
                )
    for fact in metrics["input_facts"] + metrics["derived_facts"]:
        table[fact["fact_id"]] = fact["value"]
    return lambda fid: table.get(fid)


def test_every_derived_fact_is_contract_valid(acme):
    facts = compute_metrics(acme)["derived_facts"]
    assert facts, "compute_metrics must publish its derived facts"
    for fact in facts:
        FinancialFact.model_validate(fact)


def test_every_derived_fact_recomputes(acme):
    metrics = compute_metrics(acme)
    resolve = _resolver(metrics, acme)
    checked = 0
    for fact in metrics["derived_facts"]:
        if fact["derivation"].get("recomputable") is False:
            continue  # the reverse DCF is a bisection, not an expression
        again = recompute(fact, resolve)
        assert again is not None, f"{fact['fact_id']} could not be recomputed"
        assert again == pytest.approx(fact["value"], rel=1e-9, abs=1e-9), fact["fact_id"]
        checked += 1
    assert checked > 20, "the recompute check should cover most of the output"


def test_derived_fact_filed_at_is_the_latest_input(acme):
    """FCF from a FY2025 cash flow and a FY2025 capex is filed when the 10-K was."""
    metrics = compute_metrics(acme)
    by_id = {f["fact_id"]: f for f in metrics["derived_facts"]}
    assert by_id["fact:ACME:fcf:FY2025"]["filed_at"] == "2026-02-20"
    # A growth rate spans two filings: the LATER one is when it became knowable.
    assert by_id["fact:ACME:revenue_yoy:FY2025"]["filed_at"] == "2026-02-20"
    assert by_id["fact:ACME:revenue_yoy:FY2024"]["filed_at"] == "2025-02-21"
    # And a market-based multiple is dated by the quote, not by the filing.
    assert by_id["fact:ACME:pe:FY2025"]["filed_at"] == "2026-09-19"


def test_filed_at_rule_takes_the_maximum():
    from calc.lineage import FactRef

    inputs = [
        FactRef("fact:X:op_cash_flow:FY2025", "op_cash_flow", "FY2025", 1.0, "2025-10-30"),
        FactRef("fact:X:capex:FY2025", "capex", "FY2025", 1.0, "2026-02-01"),
    ]
    assert latest_filed_at(inputs) == "2026-02-01"


def test_no_derived_fact_is_filed_after_as_of(acme):
    metrics = compute_metrics(acme)
    for fact in metrics["derived_facts"] + metrics["input_facts"]:
        assert fact["filed_at"] <= metrics["as_of"], fact["fact_id"]


# --------------------------------------------------------------------------
# 3. Missing inputs
# --------------------------------------------------------------------------
def test_missing_input_yields_unavailable_not_zero(acme):
    """Blank out one input and the metric built on it must go unavailable."""
    for period in acme["financials"]:
        period["capex"] = {"value": None, "unit": "usd", "type": "fact", "status": "unavailable"}
    metrics = compute_metrics(acme)
    fcf = metrics["cash_flow"]["fcf"]
    assert fcf["value"] is None and fcf["status"] == "unavailable"
    assert "capex" in fcf["unavailable_reason"]
    assert metrics["margins"]["FY2025"]["fcf"]["value"] is None
    assert metrics["valuation"]["p_fcf"]["value"] is None
    assert metrics["reverse_dcf"]["implied_fcf_cagr"]["value"] is None
    assert metrics["reverse_dcf"]["sensitivity_grid"], "the grid must still be present"
    # and nothing citing it may be published as a fact
    assert not [f for f in metrics["derived_facts"] if f["metric"] == "fcf"]


def test_zero_revenue_does_not_raise(acme):
    for period in acme["financials"]:
        period["revenue"] = {"value": 0.0, "unit": "usd", "type": "fact", "status": "ok"}
    metrics = compute_metrics(acme)
    assert metrics["margins"]["FY2025"]["gross"]["value"] is None
    assert metrics["growth"]["FY2025"]["revenue_yoy"]["value"] is None


def test_a_factsheet_with_one_year_still_computes(acme):
    acme["financials"] = [p for p in acme["financials"] if p["period"] == "FY2025"]
    metrics = compute_metrics(acme)
    assert metrics["cash_flow"]["fcf"]["value"] == 600_000_000
    assert metrics["growth"] == {}
    assert metrics["cagr"]["years"] == 0
    assert metrics["per_share"]["dilution_yoy"]["status"] == "unavailable"


# --------------------------------------------------------------------------
# 4. The real recordings
# --------------------------------------------------------------------------
def test_every_real_factsheet_computes(real_factsheet):
    metrics = compute_metrics(real_factsheet)
    Metrics.model_validate(metrics)
    for fact in metrics["derived_facts"]:
        FinancialFact.model_validate(fact)


def test_real_recompute_holds(real_factsheet):
    metrics = compute_metrics(real_factsheet)
    resolve = _resolver(metrics, real_factsheet)
    for fact in metrics["derived_facts"]:
        if fact["derivation"].get("recomputable") is False:
            continue
        again = recompute(fact, resolve)
        assert again is not None, f"{fact['fact_id']} unresolvable"
        assert again == pytest.approx(fact["value"], rel=1e-9, abs=1e-6), fact["fact_id"]


def test_split_gap_makes_per_share_growth_unavailable():
    """NVDA's share count rises 9.9x into FY2023; EPS growth across it is refused."""
    metrics = compute_metrics(load_real("NVDA"))
    eps = metrics["growth"]["FY2023"]["eps_yoy"]
    assert eps["status"] == "unavailable"
    assert "share" in eps["unavailable_reason"]
    # Totals are unaffected.
    assert metrics["growth"]["FY2023"]["revenue_yoy"]["value"] is not None
    assert metrics["cagr"]["revenue"]["value"] is not None
    # And the CAGR that spans the boundary is refused too.
    assert metrics["cagr"]["eps_diluted"]["status"] == "unavailable"
    # while a year on one side of it is fine
    assert metrics["growth"]["FY2025"]["eps_yoy"]["value"] is not None


def test_aapl_interest_coverage_is_unavailable_not_zero():
    """Apple tags no interest expense; coverage must not read as distress."""
    coverage = compute_metrics(load_real("AAPL"))["balance_sheet"]["interest_coverage"]
    assert coverage["value"] is None and coverage["status"] == "unavailable"
    assert "interest_expense" in coverage["unavailable_reason"]


def test_bank_gets_book_value_not_free_cash_flow():
    jpm = load_real("JPM")
    assert is_partial_scope(jpm)
    metrics = compute_metrics(jpm)
    for path in (
        metrics["cash_flow"]["fcf"],
        metrics["margins"]["FY2025"]["gross"],
        metrics["valuation"]["ev_ebitda"],
        metrics["valuation"]["ev_revenue"],
    ):
        assert path["value"] is None
        assert path["not_applicable"] is True, path
    assert metrics["valuation"]["primary_multiple"] == "p_b"
    assert metrics["valuation"]["p_b"]["value"] > 0
    assert metrics["per_share"]["book_value_per_share"]["value"] > 0
    assert metrics["returns"]["roe"]["value"] > 0
    assert metrics["scope_level"] == "partial"


def test_not_applicable_is_distinguishable_from_missing():
    """A bank's FCF and a filer's untagged line must not look the same."""
    jpm = compute_metrics(load_real("JPM"))
    aapl = compute_metrics(load_real("AAPL"))
    assert jpm["cash_flow"]["fcf"].get("not_applicable") is True
    assert aapl["balance_sheet"]["interest_coverage"].get("not_applicable") is None
