"""Contract-model tests: round-trips, provenance, derivation, claims, tool as_of.

These exercise the pydantic models directly, which is where the rules that
JSON Schema cannot express are enforced.
"""

import pytest
from helpers import MODEL_ONLY_FIXTURES, load_fixture
from pydantic import TypeAdapter, ValidationError

from schema.contracts import (
    Analysis,
    Claim,
    CompanyProfile,
    Factsheet,
    Filing,
    FinancialFact,
    MarketSnapshot,
    Metrics,
    Peer,
    ResearchState,
    ScenarioResult,
    Scenarios,
    ScenarioWeights,
    Verdict,
    VerificationResult,
)
from schema.contracts.state import SECTION_OWNERS
from schema.contracts.tools import COMPUTE_TOOLS, TOOL_REQUESTS, TOOL_RESPONSES

FACT_LIST = TypeAdapter(list[FinancialFact])
FILING_LIST = TypeAdapter(list[Filing])
PEER_LIST = TypeAdapter(list[Peer])

ROUND_TRIP = {
    "factsheet.json": Factsheet,
    "metrics.json": Metrics,
    "scenarios.json": Scenarios,
    "scenario_result.json": ScenarioResult,
    "analysis_financial.json": Analysis,
    "analysis_business.json": Analysis,
    "analysis_valuation.json": Analysis,
    "analysis_red_team.json": Analysis,
    "audit.json": VerificationResult,
    "verdict.json": Verdict,
    "research_state.json": ResearchState,
    "market_snapshot.json": MarketSnapshot,
    "company_profile.json": CompanyProfile,
    "scenario_weights_clamped.json": ScenarioWeights,
}


# --------------------------------------------------------------------------
# Serialization round-trips
# --------------------------------------------------------------------------
@pytest.mark.parametrize("fixture,model", sorted(ROUND_TRIP.items(), key=lambda kv: kv[0]))
def test_fixture_round_trips_through_its_model(fixture, model):
    raw = load_fixture(fixture)
    parsed = model.model_validate(raw)
    again = model.model_validate(parsed.model_dump(mode="json"))
    assert again.model_dump(mode="json") == parsed.model_dump(mode="json")


def test_json_round_trip_is_stable():
    fs = Factsheet.model_validate(load_fixture("factsheet.json"))
    assert Factsheet.model_validate_json(fs.model_dump_json()).model_dump() == fs.model_dump()


@pytest.mark.parametrize(
    "fixture,adapter",
    [("facts.json", FACT_LIST), ("filings.json", FILING_LIST), ("peers.json", PEER_LIST)],
)
def test_list_fixture_round_trips(fixture, adapter):
    raw = load_fixture(fixture)
    parsed = adapter.validate_python(raw)
    assert len(parsed) == len(raw)
    dumped = adapter.dump_python(parsed, mode="json")
    again = adapter.dump_python(adapter.validate_python(dumped), mode="json")
    assert again == dumped


def test_model_only_fixtures_are_all_covered():
    assert MODEL_ONLY_FIXTURES <= set(ROUND_TRIP) | {"facts.json", "filings.json", "peers.json"}


# --------------------------------------------------------------------------
# FinancialFact: provenance and derivation
# --------------------------------------------------------------------------
def _sample_fact(**overrides):
    base = {
        "fact_id": "fact:ACME:revenue:FY2025",
        "company_id": "ACME",
        "metric": "revenue",
        "xbrl_concept": "Revenues",
        "value": 5_000_000_000.0,
        "unit": "usd",
        "currency": "USD",
        "scale": "units",
        "period_type": "duration",
        "period_start": "2025-01-01",
        "period_end": "2025-12-31",
        "fiscal_period": "FY2025",
        "filing_type": "10-K",
        "accession_number": "0001234567-26-000010",
        "filed_at": "2026-02-20",
        "retrieved_at": "2026-09-19T12:00:00Z",
        "source_kind": "xbrl_reported",
    }
    base.update(overrides)
    return base


def test_every_committed_fact_has_provenance():
    for fact in FACT_LIST.validate_python(load_fixture("facts.json")):
        assert fact.retrieved_at
        if fact.source_kind.value in ("xbrl_reported", "filing_text"):
            assert fact.accession_number and fact.filed_at, fact.fact_id
        elif fact.source_kind.value == "derived":
            assert fact.derivation is not None, fact.fact_id


def test_reported_fact_requires_an_accession():
    with pytest.raises(ValidationError, match="accession_number"):
        FinancialFact.model_validate(_sample_fact(accession_number=None))


def test_reported_fact_requires_filed_at_for_point_in_time():
    with pytest.raises(ValidationError, match="filed_at"):
        FinancialFact.model_validate(_sample_fact(filed_at=None))


def test_derived_fact_requires_a_derivation():
    with pytest.raises(ValidationError, match="requires a derivation"):
        FinancialFact.model_validate(
            _sample_fact(source_kind="derived", accession_number=None, filed_at=None)
        )


def test_only_derived_facts_may_carry_a_derivation():
    with pytest.raises(ValidationError, match="only source_kind 'derived'"):
        FinancialFact.model_validate(
            _sample_fact(
                derivation={"formula": "a - b", "input_fact_ids": ["fact:ACME:a:FY2025"]}
            )
        )


def test_derivation_requires_input_fact_ids():
    with pytest.raises(ValidationError):
        FinancialFact.model_validate(
            _sample_fact(
                source_kind="derived", accession_number=None, filed_at=None,
                derivation={"formula": "a - b", "input_fact_ids": []},
            )
        )


def test_instant_fact_must_not_have_a_period_start():
    with pytest.raises(ValidationError, match="must not have a period_start"):
        FinancialFact.model_validate(_sample_fact(period_type="instant"))


def test_duration_fact_requires_a_period_start():
    with pytest.raises(ValidationError, match="require a period_start"):
        FinancialFact.model_validate(_sample_fact(period_start=None))


def test_fact_fraction_is_not_a_percent():
    with pytest.raises(ValidationError, match="looks like a percent"):
        FinancialFact.model_validate(_sample_fact(unit="fraction", value=25.0, currency=None))


def test_fact_cannot_supersede_itself():
    with pytest.raises(ValidationError, match="cannot supersede itself"):
        FinancialFact.model_validate(_sample_fact(superseded_by="fact:ACME:revenue:FY2025"))


def test_fixtures_contain_exactly_one_restatement_and_one_derived_fact():
    facts = FACT_LIST.validate_python(load_fixture("facts.json"))
    superseded = [f for f in facts if f.superseded_by]
    derived = [f for f in facts if f.source_kind.value == "derived"]
    assert len(superseded) == 1 and not superseded[0].is_current
    assert len(derived) == 1 and derived[0].derivation.formula == "op_cash_flow - capex"
    # The restated row must point at a fact that actually exists.
    ids = {f.fact_id for f in facts}
    assert superseded[0].superseded_by in ids


# --------------------------------------------------------------------------
# Claim: no bare numbers
# --------------------------------------------------------------------------
def _sample_claim(**overrides):
    base = {
        "claim_id": "claim:financial:test",
        "text": "Free cash flow grew.",
        "fact_ids": ["fact:ACME:fcf:FY2025"],
        "derived_by": "code",
    }
    base.update(overrides)
    return base


def test_claim_with_a_value_must_cite_fact_ids():
    with pytest.raises(ValidationError, match="must cite at least one"):
        Claim.model_validate(
            _sample_claim(
                fact_ids=[],
                value={
                    "value": 1.0, "unit": "usd", "type": "fact",
                    "status": "ok", "source_id": "src:market:quote",
                },
            )
        )


def test_claim_with_a_bare_number_in_prose_is_rejected():
    with pytest.raises(ValidationError, match="cite no fact_ids"):
        Claim.model_validate(
            _sample_claim(text="Free cash flow reached 600 million.", fact_ids=[])
        )


def test_claim_number_backed_by_an_evidence_quote_is_accepted():
    """A numeral the verifier can string-match against a filing is traceable."""
    ok = Claim.model_validate(
        _sample_claim(
            text="Senior notes mature in fiscal 2027.",
            fact_ids=[],
            derived_by="agent",
            section_ids=["sec:0001234567-26-000010:debt_note"],
            evidence=[
                {
                    "quote": "consisting of $400 million of 4.25% senior notes due fiscal 2027",
                    "source_id": "src:edgar:0001234567-26-000010:debt_note",
                }
            ],
        )
    )
    assert ok.unsourced_numbers == []


def test_spelled_out_numbers_do_not_need_fact_ids():
    ok = Claim.model_validate(
        _sample_claim(
            text="Two large customers received longer payment terms.",
            fact_ids=[],
            derived_by="agent",
            section_ids=["sec:0001234567-26-000010:mdna"],
        )
    )
    assert ok.has_number is False


def test_qualitative_agent_claim_must_cite_something():
    with pytest.raises(ValidationError, match="must cite section_ids or evidence"):
        Claim.model_validate(
            _sample_claim(text="The moat is wide.", fact_ids=[], derived_by="agent")
        )


def test_every_committed_claim_is_traceable():
    state = ResearchState.model_validate(load_fixture("research_state.json"))
    assert state.all_claims, "the ACME research state should carry claims"
    for claim in state.all_claims:
        assert claim.unsourced_numbers == [], claim.claim_id
        if claim.value is not None:
            assert claim.fact_ids, claim.claim_id


# --------------------------------------------------------------------------
# ResearchState
# --------------------------------------------------------------------------
def test_research_state_has_all_fourteen_sections():
    state = ResearchState.model_validate(load_fixture("research_state.json"))
    assert [s.section_key for s in state.sections.as_list()] == list(SECTION_OWNERS)


def test_section_owner_must_match_the_canonical_routing_map():
    state = ResearchState.model_validate(load_fixture("research_state.json"))
    for section in state.sections.as_list():
        assert section.owner is SECTION_OWNERS[section.section_key]


def test_section_owner_cannot_be_reassigned_silently():
    raw = load_fixture("research_state.json")
    raw["sections"]["valuation"]["owner"] = "business"
    with pytest.raises(ValidationError, match="is owned by"):
        ResearchState.model_validate(raw)


def test_duplicate_claim_ids_are_rejected():
    raw = load_fixture("research_state.json")
    dup = dict(raw["sections"]["catalysts"]["claims"][0])
    dup["claim_id"] = raw["sections"]["risks"]["claims"][0]["claim_id"]
    raw["sections"]["catalysts"]["claims"] = [dup]
    with pytest.raises(ValidationError, match="duplicate claim_id"):
        ResearchState.model_validate(raw)


def test_state_version_is_recorded():
    state = ResearchState.model_validate(load_fixture("research_state.json"))
    assert state.state_version


# --------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------
def test_audit_cannot_pass_with_an_error_issue():
    raw = load_fixture("audit.json")
    raw["issues"][0]["severity"] = "error"
    with pytest.raises(ValidationError, match="severity 'error'"):
        VerificationResult.model_validate(raw)


def test_deterministic_check_cannot_be_attributed_to_an_llm():
    raw = load_fixture("audit.json")
    raw["issues"][0]["checked_by_llm"] = True
    with pytest.raises(ValidationError, match="deterministic check"):
        VerificationResult.model_validate(raw)


def test_verdict_card_cannot_disagree_with_calc():
    raw = load_fixture("verdict.json")
    raw["card"]["scores"]["long_term"] = 9
    with pytest.raises(ValidationError, match="card.scores does not match"):
        Verdict.model_validate(raw)


# --------------------------------------------------------------------------
# Tools: point-in-time by construction
# --------------------------------------------------------------------------
def test_every_data_tool_request_requires_as_of():
    for name, model in TOOL_REQUESTS.items():
        if name in COMPUTE_TOOLS:
            continue
        field = model.model_fields.get("as_of")
        assert field is not None, f"{name}: every data tool must take as_of (ADR 0003)"
        assert field.is_required(), f"{name}: as_of must be required, not defaulted"


def test_compute_tools_do_not_take_as_of():
    """A function given a factsheet must not take a second, possibly conflicting date."""
    for name in COMPUTE_TOOLS:
        assert "as_of" not in TOOL_REQUESTS[name].model_fields, name


def test_the_eleven_tools_are_exactly_paired():
    assert set(TOOL_REQUESTS) == set(TOOL_RESPONSES)
    assert len(TOOL_REQUESTS) == 11


def test_tool_requests_reject_unknown_arguments():
    with pytest.raises(ValidationError):
        TOOL_REQUESTS["get_market_snapshot"].model_validate(
            {"ticker": "ACME", "as_of": "2026-09-19", "sneaky": True}
        )
