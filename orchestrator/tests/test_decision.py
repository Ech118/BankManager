"""Step 5 at the coordinator: scenario -> red team -> calc -> synthesizer -> audit -> Verdict."""

import json
import re

import pytest

from agents import client
from orchestrator import events, scenario_claims
from orchestrator.coordinator import ConsistencyError, Coordinator, VerifierUnavailable
from orchestrator.mcp_client import InMemoryMcpClient
from schema.contracts.enums import AgentName
from schema.contracts.scenario_result import ScenarioResult
from schema.contracts.verdict import Verdict
from tests.e2e.support.fake_calc import MOCK, FakeCalc, factsheet_provider, simple_auditor
from tests.e2e.support.fake_mcp import build_fake_server


@pytest.fixture()
def mcp():
    c = InMemoryMcpClient(build_fake_server())
    yield c
    c.close()


class Llm:
    """The real MockLLM, with per-agent edits and a record of every prompt."""

    def __init__(self, monkeypatch, **edits):
        self.calls, self.edits, self.real = [], edits, client.complete
        monkeypatch.setattr(client, "complete", self)

    def __call__(self, agent, system, user, max_tokens=4096, schema=None, kind="analysis"):
        self.calls.append({"agent": agent.value, "kind": kind, "user": user, "system": system})
        res = self.real(agent, system, user, max_tokens=max_tokens, schema=schema, kind=kind)
        edit = self.edits.get(agent.value)
        if edit and kind == "analysis":
            n = sum(1 for c in self.calls if c["agent"] == agent.value and c["kind"] == "analysis")
            res["text"] = json.dumps(edit(json.loads(res["text"]), n))
        return res

    def prompts(self, agent):
        return [c["user"] for c in self.calls if c["agent"] == agent and c["kind"] == "analysis"]


def coordinator(mcp, calc=None, run_id="r", **kw):
    return Coordinator(
        mcp,
        calc=calc or FakeCalc(),
        factsheet=factsheet_provider,
        auditor=simple_auditor,
        run_id=run_id,
        **kw,
    )


def test_the_whole_pipeline_produces_a_contract_valid_verdict_with_six_agents(mcp, monkeypatch):
    Llm(monkeypatch)
    v = coordinator(mcp).run("ACME", "2026-09-19")
    Verdict.model_validate(v.model_dump(mode="json"))
    assert {a.value for a in v.agent_outputs} == {
        "financial",
        "business",
        "valuation",
        "scenario",
        "red_team",
        "synthesizer",
    }
    assert len(v.sections) == 14 and v.audit.passed and v.disclaimer
    assert v.card.verdict == "avoid" and v.card.ticker == "ACME"


def test_every_number_on_the_card_comes_from_calc_not_from_a_model(mcp, monkeypatch):
    def greedy(d, n):
        d["synthesis"]["thesis"] = (
            "Scores are perfect. The stock will double. Buy it all."  # numerals would be rejected
        )
        return d

    Llm(monkeypatch)
    calc = FakeCalc()
    v = coordinator(mcp, calc).run("ACME", "2026-09-19")
    sr = ScenarioResult.model_validate(
        calc.evaluate_scenarios(calc.calls["evaluate_scenarios"][0]["scenarios"], {}, {}, None)
    )
    assert (
        v.card.scores.model_dump()
        == json.loads((MOCK / "scenario_result.json").read_text())["scores"]
    )
    assert v.card.p_beat_sp500_5y == v.scenario_result.p_beat_sp500.long_term
    assert v.card.expected_5y_return.value == v.scenario_result.expected_annualized_return.value
    assert v.card.price.value == 50.0 and sr.scores  # price comes from the market snapshot


def test_the_scenario_proposal_reaches_calc_without_any_eps_a_model_or_p3_would_compute(
    mcp, monkeypatch
):
    Llm(monkeypatch)
    calc = FakeCalc()
    coordinator(mcp, calc).run("ACME", "2026-09-19")
    (call,) = calc.calls["evaluate_scenarios"]
    for case in ("bear", "base", "bull"):
        eps = call["scenarios"]["scenarios"][case]["eps_at_horizon"]
        assert eps["status"] == "unavailable" and eps["value"] is None and eps["derived_from"]
    assert call["scenarios"]["ticker"] == "ACME"


def test_both_prior_shifts_are_passed_to_calc_and_the_sum_is_capped(mcp, monkeypatch):
    def rt(d, n):
        d["prior_shift"] = {"value": -0.1, "reason": "Refinancing wall."}
        return d

    Llm(monkeypatch, red_team=rt)
    calc = FakeCalc()
    v = coordinator(mcp, calc).run("ACME", "2026-09-19")
    (call,) = calc.calls["evaluate_scenarios"]
    assert [(s["source"], s["value"]) for s in call["prior_shifts"]] == [
        ("scenario", -0.1),
        ("red_team", -0.1),
    ]
    prior = v.scenario_result.prior
    assert (
        prior.requested_shift == pytest.approx(-0.2) and prior.applied_shift == -0.15
    )  # capped, both recorded
    assert v.card.p_beat_sp500_5y == pytest.approx(0.42 - 0.15)


def test_the_red_team_runs_after_the_scenario_agent_and_before_calc_and_the_synthesizer(
    mcp, monkeypatch
):
    Llm(monkeypatch)
    run_id = events.new_run()
    coordinator(mcp, run_id=run_id).run("ACME", "2026-09-19")
    seq = [(getattr(e.agent, "value", e.agent), e.status) for e in events.history(run_id)]
    at = {
        step: seq.index(step)
        for step in [
            ("scenario", "running"),
            ("red_team", "running"),
            ("calc", "running"),
            ("calc", "done"),
            ("synthesizer", "running"),
            ("verify", "running"),
        ]
    }
    assert (
        at[("scenario", "running")]
        < at[("red_team", "running")]
        < at[("calc", "running")]
        < at[("calc", "done")]
        < at[("synthesizer", "running")]
        < at[("verify", "running")]
    )


def test_each_later_agent_sees_what_the_earlier_ones_found_but_the_red_team_never_sees_calc(
    mcp, monkeypatch
):
    llm = Llm(monkeypatch)
    coordinator(mcp).run("ACME", "2026-09-19")
    assert "premium to the peer median" in llm.prompts("scenario")[0]  # valuation's finding
    (red,) = llm.prompts("red_team")
    assert "bear case is a coherent story" in red  # the scenario agent's finding
    assert "CALCULATION RESULTS" not in red  # calc has not run yet
    (synth,) = llm.prompts("synthesizer")
    assert "CALCULATION RESULTS" in synth
    assert "refinancing" in synth.lower() or "de-rating" in synth.lower()  # the red team's finding


def test_a_verdict_that_contradicts_calc_is_sent_back_once_and_can_recover(mcp, monkeypatch):
    def flip(d, n):
        if n == 1:
            d["synthesis"]["verdict"] = "strong_buy"
        return d

    llm = Llm(monkeypatch, synthesizer=flip)
    run_id = events.new_run()
    calc = FakeCalc()
    v = coordinator(mcp, calc, run_id=run_id).run("ACME", "2026-09-19")
    assert calc.calls["validate_consistency"] == ["strong_buy", "avoid"]
    assert v.card.verdict == "avoid"
    retry_prompt = llm.prompts("synthesizer")[1]
    assert (
        "Consistency check failed" in retry_prompt
        and "below the S&P 500 assumption" in retry_prompt
    )
    assert any(
        e.status == "retrying" and e.agent is AgentName.SYNTHESIZER for e in events.history(run_id)
    )


def test_a_verdict_that_stays_inconsistent_fails_the_run_and_ships_nothing(mcp, monkeypatch):
    def stubborn(d, n):
        d["synthesis"]["verdict"] = "strong_buy"
        return d

    Llm(monkeypatch, synthesizer=stubborn)
    with pytest.raises(ConsistencyError, match="contradicted calc's numbers twice"):
        coordinator(mcp).run("ACME", "2026-09-19")


def test_calc_rejecting_the_proposal_fails_the_run_at_the_calc_step(mcp, monkeypatch):
    class Strict(FakeCalc):
        def evaluate_scenarios(self, *a, **k):
            raise ValueError("Scenario probabilities must sum to 1.0, got 1.1")

    Llm(monkeypatch)
    run_id = events.new_run()
    with pytest.raises(ValueError, match="must sum to 1.0"):
        coordinator(mcp, Strict(), run_id=run_id).run("ACME", "2026-09-19")
    seq = {(getattr(e.agent, "value", e.agent), e.status) for e in events.history(run_id)}
    assert ("calc", "failed") in seq and ("synthesizer", "running") not in seq


def test_scenario_and_comparison_claims_are_generated_by_code_from_calcs_result(mcp, monkeypatch):
    Llm(monkeypatch)
    v = coordinator(mcp).run("ACME", "2026-09-19")
    body = {s.id: s.body_markdown for s in v.sections}
    assert "The bear case price target is the value shown." in body["scenarios"]
    assert "trails the assumed index return" in body["sp500_comparison"]
    for section in ("scenarios", "sp500_comparison"):
        text = " ".join(re.findall(r"- ([^(\n_]*)", body[section]))
        assert not re.search(
            r"\d", text.replace("fact:ACME:eps_diluted:FY2025", "")
        )  # no numerals in the sentences


def test_clamped_weights_are_disclosed_in_a_generated_claim():
    sr = ScenarioResult.model_validate(json.loads((MOCK / "scenario_result.json").read_text()))
    facts = json.loads((MOCK / "facts.json").read_text())
    assert "within the permitted band" in scenario_claims.build(sr, facts)["scenarios"][0].text
    sr.weights.any_clamped = True  # what calc reports after bounding a weight
    assert "adjusted by code" in scenario_claims.build(sr, facts)["scenarios"][0].text


def test_the_generated_claims_cite_a_fact_because_the_contract_requires_one_for_any_number(
    mcp, monkeypatch
):
    Llm(monkeypatch)
    st = coordinator(mcp).run_state("ACME", "2026-09-19")
    code_claims = [c for c in st.all_claims if c.derived_by.value == "code"]
    assert {c.claim_id for c in code_claims} >= {
        "claim:scenario:weights",
        "claim:scenario:target-bear",
        "claim:scenario:target-base",
        "claim:scenario:target-bull",
        "claim:scenario:excess",
    }
    for claim in code_claims:
        if claim.value is not None:
            assert claim.fact_ids == ["fact:ACME:eps_diluted:FY2025"]


def test_the_verdicts_red_team_block_is_the_red_teams_case_answered_by_the_synthesizer(
    mcp, monkeypatch
):
    Llm(monkeypatch)
    v = coordinator(mcp).run("ACME", "2026-09-19")
    assert v.red_team.summary == v.agent_outputs[AgentName.RED_TEAM].summary
    assert (
        "R1:" in v.red_team.responses_by_synthesizer
        and "R2:" in v.red_team.responses_by_synthesizer
    )
    assert v.red_team.drawdown_path


def test_the_audit_sees_the_decision_claims(mcp, monkeypatch):
    Llm(monkeypatch)
    seen = {}

    def spy(state, fs, get_text, verify_claim):
        seen["sections"] = {k: len(s["claims"]) for k, s in state["sections"].items()}
        return simple_auditor(state, fs, get_text, verify_claim)

    Coordinator(mcp, calc=FakeCalc(), factsheet=factsheet_provider, auditor=spy).run(
        "ACME", "2026-09-19"
    )
    assert all(seen["sections"][k] for k in ("scenarios", "sp500_comparison", "risks", "decision"))


def test_the_decision_stages_need_calc_and_a_factsheet(mcp):
    with pytest.raises(VerifierUnavailable, match="calc"):
        Coordinator(mcp, calc=FakeCalc()).run_decision(None, {})


def test_without_calc_only_the_three_analysis_agents_run(mcp, monkeypatch):
    llm = Llm(monkeypatch)
    st = Coordinator(mcp).run_state("ACME", "2026-09-19")
    assert {a.value for a in st.agent_outputs} == {"financial", "business", "valuation"}
    assert not any(c["agent"] in ("scenario", "red_team", "synthesizer") for c in llm.calls)


def test_the_synthesizer_is_shown_the_red_teams_points_numbered_and_must_answer_each(
    mcp, monkeypatch
):
    llm = Llm(monkeypatch)
    coordinator(mcp).run("ACME", "2026-09-19")
    (synth,) = llm.prompts("synthesizer")
    assert "RED TEAM POINTS" in synth and "R1: " in synth and "R2: " in synth


def test_run_cost_and_latency_are_recorded(mcp, monkeypatch, tmp_path):
    from agents.client import PRICES

    real = client.complete

    def priced(agent, system, user, max_tokens=4096, schema=None, kind="analysis"):
        res = real(agent, system, user, max_tokens=max_tokens, schema=schema, kind=kind)
        return {
            **res,
            "model": "claude-sonnet-5",
            "tokens_in": 1000,
            "tokens_out": 200,
            "seconds": 0.5,
        }

    monkeypatch.setattr(client, "complete", priced)
    monkeypatch.setattr(events, "RUN_LOG", tmp_path / "runs.jsonl")
    coord = coordinator(mcp)
    coord.run("ACME", "2026-09-19")
    calls = sum(a["calls"] for a in coord.stats["agents"].values())  # valuation makes two
    rate_in, rate_out = PRICES["claude-sonnet-5"]
    assert calls == 7 and coord.stats["tokens_in"] == 7000 and coord.stats["tokens_out"] == 1400
    assert coord.stats["cost_usd_estimate"] == pytest.approx(
        7 * (1000 * rate_in + 200 * rate_out) / 1e6
    )
    assert coord.stats["agents"]["synthesizer"]["cost_usd"] > 0 and coord.stats["seconds"] >= 0
    assert (
        json.loads((tmp_path / "runs.jsonl").read_text().splitlines()[-1])["cost_usd_estimate"] > 0
    )
