"""Report generator: deterministic, marks unverified claims, never shows 0 for missing data."""

import json
from pathlib import Path

import pytest

from orchestrator.report import generator as g
from schema.contracts.enums import VerificationStatus
from schema.contracts.state import ResearchState
from schema.contracts.verdict import Verdict

MOCK = Path(__file__).resolve().parents[2] / "fixtures" / "mock"


def _load(name):
    return json.loads((MOCK / name).read_text())


def full_state_dict() -> dict:
    """The frozen ACME state, plus the extras the Coordinator would have added."""
    state = _load("research_state.json")
    card = _load("verdict.json")
    state["company_name"] = card["card"]["company"]
    state["market"] = _load("market_snapshot.json")
    state["synthesis"] = {
        **{
            k: card["card"][k]
            for k in (
                "thesis",
                "primary_catalyst",
                "biggest_risk",
                "valuation",
                "business_quality",
                "financial_strength",
                "verdict",
                "ten_thousand_dollar_answer",
            )
        },
        "red_team": card["red_team"],
    }
    return state


def full_state() -> ResearchState:
    return ResearchState.model_validate(full_state_dict())


def test_render_builds_a_contract_valid_verdict_from_the_state():
    v = g.render(full_state())
    Verdict.model_validate(v.model_dump(mode="json"))
    assert (
        v.ticker == "ACME" and [s.id for s in v.sections][0] == "company" and len(v.sections) == 14
    )
    assert v.card.scores.model_dump() == full_state().scenario_result.scores.model_dump()
    assert v.card.price.value == 50.0 and v.card.verdict == "avoid"


def test_report_is_a_pure_function_of_the_state():
    a, b = g.render(full_state()), g.render(full_state())
    assert a.model_dump(mode="json") == b.model_dump(mode="json")
    assert g.render_markdown(full_state(), a) == g.render_markdown(full_state(), b)
    assert a.generated_at == full_state().created_at  # the state's own clock, not now()


def test_card_comes_first_then_the_case_against_then_sections():
    state = full_state()
    md = g.render_markdown(state, g.render(state))
    assert md.index("## Verdict: AVOID") < md.index("## The case against") < md.index("## Company")
    assert md.startswith("# Acme Corporation")


def test_disclaimer_is_present_on_every_rendered_page():
    state = full_state()
    v = g.render(state)
    full, prelim = g.render_markdown(state, v), g.render_markdown(state)
    for md in (full, prelim):
        assert md.count(g.DISCLAIMER) == 2  # top and bottom
    assert v.disclaimer == g.DISCLAIMER


def test_unavailable_values_render_as_unavailable_not_zero():
    unavailable = {
        "value": None,
        "unit": "usd",
        "type": "fact",
        "status": "unavailable",
        "source_id": None,
    }
    assert g.format_value(unavailable) == "unavailable"
    assert g.format_value(None) == "unavailable"
    d = full_state_dict()
    claim = d["sections"]["financials"]["claims"][0]
    claim["value"] = unavailable
    md = g.render_markdown(ResearchState.model_validate(d))
    assert "(unavailable · fact)" in md and "($0" not in md and "(0" not in md


@pytest.mark.parametrize(
    "value,expected",
    [
        ({"value": 0.4, "unit": "fraction"}, "40.0%"),
        ({"value": 5e9, "unit": "usd"}, "$5.00B"),
        ({"value": 600e6, "unit": "usd"}, "$600.0M"),
        ({"value": 1.48, "unit": "usd_per_share"}, "$1.48"),
        ({"value": 33.78, "unit": "multiple"}, "33.8x"),
        ({"value": 395e6, "unit": "shares"}, "395.0M shares"),
        ({"value": 51.1, "unit": "days"}, "51 days"),
        ({"value": 0.0, "unit": "fraction"}, "0.0%"),  # a real zero is still shown as zero
    ],
)
def test_format_value(value, expected):
    assert (
        g.format_value({**value, "type": "fact", "status": "ok", "source_id": "src:x:1"})
        == expected
    )


def test_value_types_are_carried_into_the_markdown():
    d = full_state_dict()
    d["sections"]["financials"]["claims"][0]["value"]["type"] = "assumption"
    assert "· assumption)" in g.render_markdown(ResearchState.model_validate(d))
    assert "· fact)" in g.render_markdown(full_state())


def test_failed_and_unverified_claims_are_rendered_with_a_marker_never_dropped():
    d = full_state_dict()
    claims = d["sections"]["earnings_quality"]["claims"]
    claims[0]["verification_status"], claims[1]["verification_status"] = "failed", "unverified"
    state = ResearchState.model_validate(d)
    section = g.render_section(state.sections.earnings_quality)
    assert section.body_markdown.count("**[UNVERIFIED]**") == 2
    assert claims[0]["text"] in section.body_markdown and claims[1]["text"] in section.body_markdown
    assert section.unverified_claim_ids == [claims[0]["claim_id"], claims[1]["claim_id"]]


def test_claims_the_verifier_has_not_seen_say_so():
    d = full_state_dict()
    d["sections"]["financials"]["claims"][0]["verification_status"] = "pending"
    md = g.render_section(ResearchState.model_validate(d).sections.financials).body_markdown
    assert "_[unchecked]_" in md
    verified = g.render_section(full_state().sections.financials).body_markdown
    assert "unchecked" not in verified and "UNVERIFIED" not in verified


def test_preliminary_report_shows_no_card_and_invents_no_verdict():
    d = full_state_dict()
    for k in ("synthesis", "market", "company_name"):
        d.pop(k)
    d["scenario_result"], d["verification"] = None, None
    state = ResearchState.model_validate(d)
    md = g.render_markdown(state)
    assert "Preliminary report" in md and "## Verdict" not in md and "The case against" not in md
    assert "no score, probability or recommendation" in md
    assert "Verification has not run" in md


def test_render_refuses_to_invent_missing_inputs():
    for drop, needle in (
        ("synthesis", "synthesis"),
        ("market", "market"),
        ("company_name", "company_name"),
    ):
        d = full_state_dict()
        d.pop(drop)
        with pytest.raises(g.ReportInputError, match=needle):
            g.render(ResearchState.model_validate(d))
    d = full_state_dict()
    d["verification"] = None
    with pytest.raises(g.ReportInputError, match="verifier must run"):
        g.render(ResearchState.model_validate(d))
    d = full_state_dict()
    d["scenario_result"] = None
    with pytest.raises(g.ReportInputError, match="scenario_result"):
        g.render(ResearchState.model_validate(d))


def test_data_quality_and_redaction_are_stated_in_the_report():
    d = full_state_dict()
    d["data_quality"] = {"overall": "partial", "gaps": ["No news available"]}
    d["redacted"] = True
    md = g.render_markdown(ResearchState.model_validate(d))
    assert "**Data quality: partial** — No news available" in md and "anonymized filing text" in md


def test_unverified_count_is_stated_at_the_end():
    d = full_state_dict()
    d["verification"]["claims_verified"], d["verification"]["claims_unverified"] = 14, 2
    state = ResearchState.model_validate(d)
    assert "**2 claim(s) could not be verified**" in g.render_markdown(state, g.render(state))


def test_clamped_scenario_weights_are_disclosed():
    state = full_state()
    v = g.render(state)
    assert "adjusted by code" not in g.render_markdown(state, v)
    v.scenario_result.weights.any_clamped = True  # what calc reports after bounding a weight
    assert "adjusted by code" in g.render_markdown(state, v)


def test_template_errors_are_loud_not_blank():
    from jinja2 import UndefinedError

    with pytest.raises(UndefinedError):
        g._env().from_string("{{ nope.missing }}").render()


def test_status_enum_members_used_by_the_renderer_exist():
    assert {
        VerificationStatus.FAILED,
        VerificationStatus.UNVERIFIED,
        VerificationStatus.PENDING,
    } <= set(VerificationStatus)


def test_ui_golden_sample_matches_the_generator():
    """web/tests/fixtures/section_bodies.md is the generator's real output; the UI tests parse it.
    If this fails, the markdown format changed: regenerate the file AND check the UI still renders it."""
    d = full_state_dict()
    claims = d["sections"]["earnings_quality"]["claims"]
    claims[0]["verification_status"], claims[1]["verification_status"] = "failed", "pending"
    d["sections"]["financials"]["claims"][0]["value"]["type"] = "assumption"
    s = ResearchState.model_validate(d)
    body = "\n\n".join(
        g.render_section(sec).body_markdown
        for sec in (s.sections.financials, s.sections.earnings_quality)
    )
    golden = (
        Path(__file__).resolve().parents[2] / "web" / "tests" / "fixtures" / "section_bodies.md"
    ).read_text()
    assert body + "\n" == golden


def test_ui_preliminary_golden_sample_matches_the_generator():
    """web/tests/fixtures/preliminary_report.md is the generator's real preliminary output."""
    state = ResearchState.model_validate(_load("research_state.json"))
    golden = (
        Path(__file__).resolve().parents[2] / "web" / "tests" / "fixtures" / "preliminary_report.md"
    ).read_text()
    assert g.render_markdown(state) == golden
