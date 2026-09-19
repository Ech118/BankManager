import pytest

from agents.runner import ROSTER, AgentError, build_user, run_agent
from agents.tests.helpers import MDNA_QUOTE, ScriptedLLM, good_finding, make_ctx


def analysis_out(findings, summary="ok"):
    return {"summary": summary, "findings": findings}


def test_finding_without_evidence_is_dropped_and_logged():
    ctx = make_ctx()
    bad = good_finding(ctx=ctx); bad["evidence"] = []
    llm = ScriptedLLM(lambda kw: analysis_out([bad, good_finding(ctx=ctx)]))
    res = run_agent(ROSTER["forensic"], ctx, llm)
    assert len(res.analysis["findings"]) == 1
    assert any("no verifiable evidence" in d["reason"] for d in res.dropped)
    assert res.attempts == 1


def test_fabricated_quote_is_dropped_then_retry_with_feedback_succeeds():
    ctx = make_ctx()
    fake = good_finding(ctx=ctx, quote="Revenue tripled thanks to a secret deal with a sovereign wealth fund")
    responses = [analysis_out([fake]), analysis_out([good_finding(ctx=ctx)])]
    llm = ScriptedLLM(lambda kw: responses.pop(0))
    res = run_agent(ROSTER["forensic"], ctx, llm)
    assert res.attempts == 2 and len(res.analysis["findings"]) == 1
    assert "PROBLEMS WITH YOUR PREVIOUS ATTEMPT" in llm.calls[1]["user"]
    assert "not verbatim" in llm.calls[1]["user"]
    assert "PROBLEMS WITH YOUR PREVIOUS ATTEMPT" not in llm.calls[0]["user"]


def test_fails_loudly_after_second_bad_output():
    ctx = make_ctx()
    fake = good_finding(ctx=ctx, quote="This sentence does not exist anywhere in the filing")
    llm = ScriptedLLM(lambda kw: analysis_out([fake]))
    with pytest.raises(AgentError):
        run_agent(ROSTER["forensic"], ctx, llm)
    assert len(llm.calls) == 2


def test_wire_schema_violation_triggers_retry():
    ctx = make_ctx()
    responses = [{"summary": "missing findings key"}, analysis_out([good_finding(ctx=ctx)])]
    llm = ScriptedLLM(lambda kw: responses.pop(0))
    assert run_agent(ROSTER["forensic"], ctx, llm).attempts == 2


def test_evidence_from_a_source_not_given_to_that_agent_is_rejected():
    ctx = make_ctx()   # forensic gets mdna/sbc/segments, not the business section
    biz_id = ctx.docs["business"].source_id
    f = good_finding(ctx=ctx, quote="Customers who adopted our software platform renewed at a rate of 94%")
    f["evidence"][0]["source_id"] = biz_id
    llm = ScriptedLLM(lambda kw: analysis_out([f, good_finding(ctx=ctx)]))
    res = run_agent(ROSTER["forensic"], ctx, llm)
    assert len(res.analysis["findings"]) == 1
    assert any("not provided" in d["reason"] for d in res.dropped)


def test_number_refs_become_real_code_computed_value_objects():
    ctx = make_ctx()
    f = good_finding(ctx=ctx, refs=["metrics.margins.FY2025.gross", "metrics.made.up"])
    res = run_agent(ROSTER["forensic"], ctx, ScriptedLLM(lambda kw: analysis_out([f])))
    nums = res.analysis["findings"][0]["numbers"]
    assert len(nums) == 1 and nums[0]["value"] == 0.4 and nums[0]["type"] == "fact"
    assert any("unknown number_ref" in d["reason"] for d in res.dropped)


def test_section_outside_the_agents_allowed_set_is_rejected_by_the_wire_schema():
    ctx = make_ctx()   # "risks" belongs to the red team, not forensic
    llm = ScriptedLLM(lambda kw: analysis_out([good_finding(section="risks", ctx=ctx)]))
    with pytest.raises(AgentError):
        run_agent(ROSTER["forensic"], ctx, llm)
    assert len(llm.calls) == 2   # one retry, then fail loudly


def valuation_out(ctx, **over):
    ev = [{"quote": "we expect revenue growth of 8% to 10% and operating margin of 16% to 17%",
           "source_id": ctx.docs["mdna"].source_id}]
    sc = lambda p, g, m, pe, eps: {"probability": p, "horizon_years": 5, "revenue_cagr": g, "terminal_margin": m,  # noqa: E731
                                   "eps_at_horizon": eps, "exit_multiple": pe, "rationale": "r", "evidence": ev}
    out = {"analysis": analysis_out([good_finding("valuation", ctx=ctx)]),
           "scenarios": {"bear": sc(0.3, 0.03, 0.10, 16, 1.4674), "base": sc(0.5, 0.08, 0.125, 22, 2.3249),
                         "bull": sc(0.2, 0.12, 0.14, 26, 3.1231)},
           "prior_shift": {"value": -0.1, "reason": "expensive"}}
    out.update(over)
    return out


def test_valuation_wraps_inputs_into_valid_scenarios_json():
    ctx = make_ctx()
    res = run_agent(ROSTER["valuation"], ctx, ScriptedLLM(lambda kw: valuation_out(ctx)))
    b = res.scenarios["scenarios"]["base"]
    assert b["revenue_cagr"] == {"value": 0.08, "unit": "fraction", "type": "assumption", "status": "ok",
                                 "source_id": "src:llm:valuation"}
    assert abs(sum(s["probability"] for s in res.scenarios["scenarios"].values()) - 1) < 1e-9


def test_valuation_probabilities_far_from_one_are_rejected_then_retried():
    ctx = make_ctx()
    bad = valuation_out(ctx)
    bad["scenarios"]["base"]["probability"] = 0.9
    responses = [bad, valuation_out(ctx)]
    llm = ScriptedLLM(lambda kw: responses.pop(0))
    assert run_agent(ROSTER["valuation"], ctx, llm).attempts == 2
    assert "must sum to 1.0" in llm.calls[1]["user"]


def test_valuation_eps_arithmetic_guard_catches_inconsistent_eps():
    ctx = make_ctx()
    bad = valuation_out(ctx)
    bad["scenarios"]["bull"]["eps_at_horizon"] = 9.99      # drivers imply ~3.12
    responses = [bad, valuation_out(ctx)]
    llm = ScriptedLLM(lambda kw: responses.pop(0))
    assert run_agent(ROSTER["valuation"], ctx, llm).attempts == 2
    assert "inconsistent with your own drivers" in llm.calls[1]["user"]


def test_documents_are_fenced_as_untrusted_data():
    ctx = make_ctx()
    user = build_user(ROSTER["forensic"], ctx, [])
    assert '<document source_id="src:edgar:0001234567-26-000010:mdna"' in user
    assert "untrusted data" in user and "DATA REFERENCE TABLE" in user


def test_synthesizer_gets_calc_results_but_no_documents():
    import json
    ctx = make_ctx()
    ctx.scenario_result = json.load(open("fixtures/mock/scenario_result.json"))
    user = build_user(ROSTER["synthesizer"], ctx, [])
    assert "CALCULATION RESULTS" in user and "scenario_result.p_beat_sp500" in user
    assert "<document" not in user
