import threading
import types

import pytest

from agents import validate
from agents.runner import AgentError
from agents.tests.helpers import ScriptedLLM, SpyMock
from calc import api as calc_api
from data import api as data_api
from orchestrator.api import run_analysis
from orchestrator.pipeline import Pipeline, PipelineError


def events_of(pipe_kwargs=None, llm=None, **kw):
    events = []
    pipe = Pipeline(llm=llm or SpyMock(), emit=lambda agent, status, **x: events.append((agent, status)),
                    **(pipe_kwargs or {}))
    return pipe, events, pipe.run("ACME", **kw)


def test_mock_run_is_schema_valid_and_passes_audit():
    v = run_analysis("ACME")
    validate.check(v, "verdict.json")
    assert v["audit"]["passed"] and v["disclaimer"] and len(v["sections"]) == 15
    assert v["card"]["verdict"] == "avoid"


def test_step_order_and_all_agents_run():
    _, ev, _ = events_of()
    started = [a for a, s in ev if s == "started"]
    assert started[:4] == ["scope", "data", "calc", "scout"]
    assert set(started[4:7]) == {"forensic", "business", "balance_sheet"}
    assert started[7:] == ["valuation", "scenarios", "red_team", "synthesizer", "audit"]


def test_analysts_run_in_parallel_not_sequentially():
    barrier = threading.Barrier(3, timeout=3)
    spy = SpyMock()
    orig = spy.complete_json

    def gated(**kw):
        if kw["agent"] in ("forensic", "business", "balance_sheet"):
            barrier.wait()          # only passes if all three analysts are in flight together
        return orig(**kw)
    spy.complete_json = gated
    Pipeline(llm=spy).run("ACME")


def test_redact_hook_is_applied_before_any_agent_sees_text():
    spy = SpyMock()
    seen_audit_text = []
    audit = types.SimpleNamespace(run_audit=lambda fs, m, a, v, get_text: (
        seen_audit_text.append(get_text(fs["filing_sections"][0]["source_id"])) or {"schema_version": "1.0.0", "passed": True, "issues": []}))
    Pipeline(llm=spy, audit=audit).run("ACME", redact=lambda t: t.replace("ACME", "COMPANY-X").replace("Acme", "Company-X"))
    docs_text = "\n".join(c["user"] for c in spy.calls if c["agent"] != "synthesizer")
    assert "COMPANY-X" in docs_text
    assert "ACME CORPORATION" not in docs_text and "Acme Corporation" not in docs_text
    assert "COMPANY-X" in seen_audit_text[0]           # the auditor verifies against the redacted text too


def test_out_of_scope_ticker_stops_before_any_llm_call():
    spy = SpyMock()
    with pytest.raises(ValueError, match="Banks"):
        Pipeline(llm=spy).run("BANKX")
    assert spy.calls == []


def test_agent_failure_propagates_and_emits_error_event():
    events = []
    def bad(kw):
        return {"summary": "x", "findings": []}          # no findings -> both attempts fail
    llm = SpyMock(edit=lambda agent, d: bad(None) if agent == "forensic" else None)
    with pytest.raises(AgentError):
        Pipeline(llm=llm, emit=lambda a, s, **k: events.append((a, s))).run("ACME")
    assert ("forensic", "error") in events


def test_numbers_on_the_card_come_from_calc_not_from_the_llm():
    def greedy(agent, d):
        if agent == "synthesizer":
            d.update(verdict="strong_buy", thesis="Scores 10/10, 99% chance, 500% return")
    _, _, v = events_of(llm=SpyMock(edit=greedy))
    sr = calc_api.evaluate_scenarios(
        __import__("json").load(open("fixtures/mock/scenarios.json")), data_api.build_factsheet("ACME"), {})
    assert v["card"]["scores"] == sr["scores"]
    assert v["card"]["p_beat_sp500_5y"] == sr["p_beat_sp500"]["5y"]
    assert v["card"]["expected_5y_return"] == sr["expected_annualized_return"]


class FlakyCalc:
    """Delegates to calc.api but fails the consistency check `fails` times."""
    def __init__(self, fails):
        self.fails, self.checks = fails, 0
    def __getattr__(self, name):
        return getattr(calc_api, name)
    def validate_consistency(self, sr, card):
        self.checks += 1
        if self.checks <= self.fails:
            return {"ok": False, "issues": ["verdict buy contradicts negative excess return"]}
        return {"ok": True, "issues": []}


def test_inconsistent_verdict_is_retried_once_with_feedback():
    spy, calc = SpyMock(), FlakyCalc(fails=1)
    Pipeline(llm=spy, calc=calc).run("ACME")
    syn = [c for c in spy.calls if c["agent"] == "synthesizer"]
    assert len(syn) == 2 and "contradicts negative excess return" in syn[1]["user"]


def test_verdict_that_stays_inconsistent_fails_loudly():
    with pytest.raises(PipelineError, match="consistency"):
        Pipeline(llm=SpyMock(), calc=FlakyCalc(fails=5)).run("ACME")


def test_stats_record_tokens_latency_and_cost_per_agent():
    def usage_llm(kw):
        return SpyMock().complete_json(**kw)[0]
    from agents.llm import Usage
    class Costed(SpyMock):
        def complete_json(self, **kw):
            d, u = super().complete_json(**kw)
            return d, Usage(model="claude-opus-5", calls=1, input_tokens=1000, output_tokens=200)
    pipe, _, _ = events_of(llm=Costed())
    assert pipe.stats["agents"]["forensic"]["input_tokens"] == 1000
    assert pipe.stats["input_tokens"] == 6000 and pipe.stats["output_tokens"] == 1200
    assert pipe.stats["cost_usd_estimate"] == pytest.approx(6 * (1000 * 5 + 200 * 25) / 1e6, abs=1e-3)
    assert pipe.stats["seconds"] >= 0 and pipe.stats["audit_passed"] is True


def test_as_of_is_passed_to_the_data_layer():
    seen = {}
    real = data_api.build_factsheet
    fake = types.SimpleNamespace(check_scope=data_api.check_scope, get_section_text=data_api.get_section_text,
                                 build_factsheet=lambda t, a=None: (seen.setdefault("as_of", a), real(t, a))[1])
    Pipeline(llm=SpyMock(), data=fake).run("ACME", as_of="2026-03-01")
    assert seen["as_of"] == "2026-03-01"
