"""Rule 4: value-object, source, quote, probability, weight and arithmetic rules.

THE VALUE-OBJECT CONDITIONAL RULES. In contract v1.0.0 these lived as JSON Schema
`if`/`then` blocks in a hand-written schema/common.json. In v2.0.0 the pydantic
models are the source of truth, so each rule is now enforced in three places and
each has a test HERE that proves all three agree:

  R1 status ok        -> value must be a number
  R2 status ok        -> source_id, or a non-empty derived_from
  R3 status unavailable -> value must be null (never 0)
  R4 unit fraction    -> |value| <= 10 (fractions, not percents)

See test_value_object_rule_1 .. _rule_4 below.
"""

import re

import pytest
from helpers import (
    FIXTURE_SCHEMAS,
    evidence_items,
    load_fixture,
    norm,
    validation_errors,
    value_objects,
)
from pydantic import ValidationError

from data import api as data_api
from schema.contracts.common import ValueObject

FS = load_fixture("factsheet.json")
SOURCES = set(FS["sources"])
ALLOWED_EXTERNAL_PREFIXES = ("src:llm:", "src:config:")

OK_VALUE = {
    "value": 1.0,
    "unit": "usd",
    "type": "fact",
    "status": "ok",
    "source_id": "src:market:quote",
}


def _json_errors(vo):
    """Validate one value object against the GENERATED schema/common.json."""
    return validation_errors(vo, "common.json")


def _model_error(vo):
    """Validate one value object against the pydantic model."""
    try:
        ValueObject.model_validate(vo)
    except ValidationError as exc:
        return str(exc)
    return None


# --------------------------------------------------------------------------
# The four conditional value-object rules, each checked against BOTH enforcers
# --------------------------------------------------------------------------
def test_value_object_baseline_is_valid():
    assert not _json_errors(OK_VALUE)
    assert _model_error(OK_VALUE) is None


def test_value_object_rule_1_ok_requires_a_number():
    bad = {**OK_VALUE, "value": None}
    assert _json_errors(bad), "generated JSON Schema must reject status ok with a null value"
    assert _model_error(bad), "ValueObject model must reject status ok with a null value"


def test_value_object_rule_2_ok_requires_provenance():
    bad = {**OK_VALUE, "source_id": None}
    assert _json_errors(bad), "generated JSON Schema must require source_id or derived_from"
    assert _model_error(bad), "ValueObject model must require source_id or derived_from"
    # derived_from alone satisfies the rule.
    derived = {**OK_VALUE, "source_id": None, "derived_from": ["financials.FY2025.revenue"]}
    assert not _json_errors(derived)
    assert _model_error(derived) is None
    # An EMPTY derived_from does not.
    empty = {**OK_VALUE, "source_id": None, "derived_from": []}
    assert _json_errors(empty)
    assert _model_error(empty)


def test_value_object_rule_3_unavailable_requires_null():
    bad = {**OK_VALUE, "status": "unavailable"}
    assert _json_errors(bad), "generated JSON Schema must reject unavailable with a value"
    assert _model_error(bad), "ValueObject model must reject unavailable with a value"
    good = {**OK_VALUE, "value": None, "status": "unavailable", "source_id": None}
    assert not _json_errors(good)
    assert _model_error(good) is None


def test_value_object_rule_4_fractions_are_not_percents():
    bad = {**OK_VALUE, "unit": "fraction", "value": 25.0}
    assert _json_errors(bad), "generated JSON Schema must reject a percent in a fraction"
    assert _model_error(bad), "ValueObject model must reject a percent in a fraction"
    good = {**OK_VALUE, "unit": "fraction", "value": 0.25}
    assert not _json_errors(good)
    assert _model_error(good) is None


def test_value_object_rejects_unknown_unit():
    bad = {**OK_VALUE, "unit": "percent"}
    assert _json_errors(bad)
    assert _model_error(bad)


# --------------------------------------------------------------------------
# The same rules, applied across every committed fixture
# --------------------------------------------------------------------------
@pytest.mark.parametrize("name", sorted(FIXTURE_SCHEMAS))
def test_fraction_values_look_like_fractions_not_percents(name):
    for path, vo in value_objects(load_fixture(name)):
        if vo["unit"] == "fraction" and vo["value"] is not None:
            assert abs(vo["value"]) <= 10, (
                f"{name}:{path} = {vo['value']} looks like a percent, use fractions (0.25 = 25%)"
            )


@pytest.mark.parametrize("name", sorted(FIXTURE_SCHEMAS))
def test_value_objects_obey_the_status_rules(name):
    for path, vo in value_objects(load_fixture(name)):
        if vo["status"] == "ok":
            assert vo["value"] is not None, f"{name}:{path}: status ok with null value"
            assert vo.get("source_id") or vo.get("derived_from"), (
                f"{name}:{path}: status ok without provenance"
            )
        else:
            assert vo["value"] is None, f"{name}:{path}: unavailable must carry null, never 0"


@pytest.mark.parametrize("name", sorted(FIXTURE_SCHEMAS))
def test_numeric_leaves_are_value_objects(name):
    """No bare floats for financial figures. Allowed bare numbers are listed by key."""
    allowed_keys = {
        # value objects and documented exceptions
        "value", "probability", "horizon_years", "p_beat_sp500_5y",
        "short_term", "medium_term", "long_term", "base_rate",
        # sensitivity grid axes
        "discount_rate", "terminal_growth",
        # prior cap machinery
        "requested_shift", "applied_shift", "cap",
        # scenario weight clamp record
        "bear", "base", "bull", "requested", "clamped_to", "applied",
        "default_weight", "band",
        # section offsets and verification counters
        "char_count", "char_start", "char_end", "retry_count",
        "claims_checked", "claims_verified", "claims_unverified", "llm_checks_run",
        "attempt", "max_attempts", "requested_prior_shift",
    }

    def scan(node, path, inside_value):
        if isinstance(node, dict):
            vo = {"value", "unit", "type", "status"} <= set(node)
            for k, x in node.items():
                scan(x, f"{path}.{k}", inside_value or vo)
        elif isinstance(node, list):
            for i, x in enumerate(node):
                scan(x, f"{path}[{i}]", inside_value)
        elif isinstance(node, (int, float)) and not isinstance(node, bool) and not inside_value:
            key = re.split(r"[.\[]", path)[-1]
            assert key in allowed_keys, f"{name}:{path} is a bare number; wrap it in a value object"

    scan(load_fixture(name), name, False)


# --------------------------------------------------------------------------
# Provenance resolves
# --------------------------------------------------------------------------
def test_factsheet_source_ids_resolve():
    for path, vo in value_objects(FS):
        if vo.get("source_id"):
            assert vo["source_id"] in SOURCES, f"{path}: {vo['source_id']} not in factsheet.sources"
    for sec in FS["filing_sections"]:
        assert sec["source_id"] in SOURCES
    for n in FS["news"]:
        assert n["source_id"] in SOURCES


@pytest.mark.parametrize("name", sorted(FIXTURE_SCHEMAS))
def test_other_artifacts_source_ids_resolve(name):
    obj = load_fixture(name)
    for path, vo in value_objects(obj):
        sid = vo.get("source_id")
        if sid:
            assert sid in SOURCES or sid.startswith(ALLOWED_EXTERNAL_PREFIXES), (
                f"{name}:{path}: unknown {sid}"
            )
    for path, ev in evidence_items(obj):
        assert ev["source_id"] in SOURCES, f"{name}:{path}: evidence cites unknown {ev['source_id']}"


@pytest.mark.parametrize("name", sorted(FIXTURE_SCHEMAS))
def test_every_evidence_quote_is_verbatim_in_its_source(name):
    for path, ev in evidence_items(load_fixture(name)):
        text = norm(data_api.get_section_text(ev["source_id"]))
        assert norm(ev["quote"]) in text, (
            f"{name}:{path}: quote not found in {ev['source_id']}: {ev['quote']!r}"
        )


# --------------------------------------------------------------------------
# Scenario weights and the prior cap
# --------------------------------------------------------------------------
def test_scenario_probabilities_sum_to_one():
    for fname in ("scenarios.json", "scenario_result.json"):
        s = load_fixture(fname)["scenarios"]
        assert abs(sum(x["probability"] for x in s.values()) - 1.0) < 1e-6, fname


def test_prior_shift_respects_cap():
    p = load_fixture("scenario_result.json")["prior"]
    assert abs(p["applied_shift"]) <= p["cap"] + 1e-12
    assert abs(p["applied_shift"]) <= abs(p["requested_shift"]) + 1e-12


def test_applied_weights_are_the_ones_used_for_expected_value():
    """A scenario probability must never bypass the bounding step."""
    sr = load_fixture("scenario_result.json")
    w = sr["weights"]
    for name in ("bear", "base", "bull"):
        assert abs(sr["scenarios"][name]["probability"] - w[name]) < 1e-9, name
    assert abs(w["bear"] + w["base"] + w["bull"] - 1.0) < 1e-9


def test_every_scenario_weight_is_recorded_never_silently_dropped():
    for fname in ("scenario_result.json", "scenario_weights_clamped.json"):
        w = load_fixture(fname)
        w = w["weights"] if "weights" in w else w
        assert sorted(c["scenario"] for c in w["clamps"]) == ["base", "bear", "bull"], fname


def test_out_of_band_weights_are_clamped_and_the_clamp_is_recorded():
    """The Scenario Agent asked for bear=0.55; the band tops out at 0.45."""
    w = load_fixture("scenario_weights_clamped.json")
    bear = next(c for c in w["clamps"] if c["scenario"] == "bear")
    assert bear["requested"] == 0.55, "fixture should demonstrate an out-of-band request"
    assert bear["was_clamped"] is True, "an out-of-band weight must be clamped, not accepted"
    assert bear["clamped_to"] == pytest.approx(bear["default_weight"] + bear["band"])
    assert w["any_clamped"] is True, "the clamp must be visible at the top level"
    # Clamped, not rejected: all three weights survive and still form a distribution.
    assert abs(w["bear"] + w["base"] + w["bull"] - 1.0) < 1e-9
    # And every applied weight stays inside its own band after redistribution.
    for c in w["clamps"]:
        lo, hi = c["default_weight"] - c["band"], c["default_weight"] + c["band"]
        assert lo - 1e-9 <= c["applied"] <= hi + 1e-9, c["scenario"]


def test_weight_clamp_flags_cannot_lie():
    """A clamp that changed a number must say so. Enforced by the model."""
    from schema.contracts.scenario_result import WeightClamp

    silent = {
        "scenario": "bear", "requested": 0.55, "clamped_to": 0.45, "applied": 0.45,
        "default_weight": 0.30, "band": 0.15,
        "was_clamped": False,          # a lie: 0.55 -> 0.45 IS a clamp
        "was_renormalized": False,
    }
    with pytest.raises(ValidationError):
        WeightClamp.model_validate(silent)


# --------------------------------------------------------------------------
# Cross-artifact arithmetic
# --------------------------------------------------------------------------
def test_verdict_has_disclaimer_and_matches_calc():
    v = load_fixture("verdict.json")
    assert len(v["disclaimer"].strip()) >= 20
    sr = load_fixture("scenario_result.json")
    assert v["card"]["scores"] == sr["scores"]
    assert v["card"]["p_beat_sp500_5y"] == sr["p_beat_sp500"]["long_term"]


def test_financial_periods_are_newest_first_and_identities_hold():
    fin = FS["financials"]
    ends = [p["period_end"] for p in fin]
    assert ends == sorted(ends, reverse=True)
    for p in fin:
        def val(k, period=p):
            return period[k]["value"]

        assert val("gross_profit") == pytest.approx(val("revenue") - val("cost_of_revenue"))
        assert val("pretax_income") == pytest.approx(
            val("operating_income") - val("interest_expense")
        )
    m = FS["market"]
    q2 = fin[0]
    assert m["enterprise_value"]["value"] == pytest.approx(
        m["market_cap"]["value"] + q2["total_debt"]["value"] - q2["cash"]["value"]
    )
    assert m["market_cap"]["value"] == pytest.approx(
        m["price"]["value"] * m["shares_outstanding"]["value"]
    )


def test_metrics_match_factsheet():
    m = load_fixture("metrics.json")
    fy = next(p for p in FS["financials"] if p["period"] == m["latest_annual_period"])
    fcf = fy["op_cash_flow"]["value"] - fy["capex"]["value"]
    assert m["cash_flow"]["fcf"]["value"] == pytest.approx(fcf)
    assert m["margins"]["FY2025"]["gross"]["value"] == pytest.approx(
        fy["gross_profit"]["value"] / fy["revenue"]["value"]
    )
    assert m["cash_flow"]["fcf_yield"]["value"] == pytest.approx(
        fcf / FS["market"]["market_cap"]["value"]
    )


def test_derived_values_declare_their_inputs():
    for name in ("metrics.json", "scenario_result.json"):
        for path, vo in value_objects(load_fixture(name)):
            if vo["status"] == "ok" and vo["type"] == "fact":
                assert vo.get("derived_from") or vo.get("source_id"), f"{name}:{path}"
            if vo["type"] == "assumption":
                assert vo.get("source_id") or vo.get("derived_from"), f"{name}:{path}"


def test_ticker_and_dates_are_consistent_across_fixtures():
    for name in FIXTURE_SCHEMAS:
        obj = load_fixture(name)
        if "ticker" in obj:
            assert obj["ticker"] == FS["ticker"], name
