"""Step 4 at the coordinator: valuation runs after the pair, reads their findings, and can be retried."""

import json
import threading
from pathlib import Path

import pytest

from agents import client
from agents.tests.helpers import DEFAULT_PLAN, analysis_payload, finding
from agents.tests.test_valuation_agent import analysis as val_analysis
from agents.tests.test_valuation_agent import vfinding
from orchestrator import events
from orchestrator.coordinator import Coordinator
from orchestrator.mcp_client import InMemoryMcpClient, McpToolError
from orchestrator.report import generator
from schema.contracts.enums import AgentName, VerificationStatus
from tests.e2e.support.fake_mcp import build_fake_server

FACTSHEET = Path(__file__).resolve().parents[2] / "fixtures" / "mock" / "factsheet.json"
BUSINESS_ID = "src:edgar:0001234567-26-000010:business"
FIN_CLAIM = "Gross margin expanded because software mix rose."
BIZ_CLAIM = "Customers renew at a high rate."


@pytest.fixture()
def mcp():
    c = InMemoryMcpClient(build_fake_server())
    yield c
    c.close()


class Models:
    def __init__(self, monkeypatch, valuation=None):
        self.calls, self.lock = [], threading.Lock()
        self.valuation = valuation or (lambda n: val_analysis(vfinding()))
        monkeypatch.setattr(client, "complete", self)

    def __call__(self, agent, system, user, max_tokens=4096, schema=None, kind="analysis"):
        with self.lock:
            self.calls.append({"agent": agent.value, "kind": kind, "user": user})
            n = sum(1 for c in self.calls if c["agent"] == agent.value and c["kind"] == kind)
        if kind == "plan":
            out = DEFAULT_PLAN
        elif agent.value == "valuation":
            out = self.valuation(n)
        elif agent.value == "business":
            out = analysis_payload(
                finding(
                    claim=BIZ_CLAIM,
                    quote="renewed at a rate of 94%",
                    source_id=BUSINESS_ID,
                    fact_ids=(),
                    section="competitive_position",
                ),
                summary="BIZ-SUMMARY",
            )
        else:
            out = analysis_payload(
                finding(claim=FIN_CLAIM, section="financials"), summary="FIN-SUMMARY"
            )
        return {
            "text": json.dumps(out),
            "model": "t",
            "tokens_in": 10,
            "tokens_out": 5,
            "seconds": 0.0,
        }

    def prompts(self, agent, kind="analysis"):
        return [c["user"] for c in self.calls if c["agent"] == agent and c["kind"] == kind]


def test_valuation_starts_only_after_both_analysts_are_done(mcp, monkeypatch):
    Models(monkeypatch)
    run_id = events.new_run()
    Coordinator(mcp, run_id=run_id).run_state("ACME")
    seq = [(getattr(e.agent, "value", e.agent), e.status) for e in events.history(run_id)]
    val_start = seq.index(("valuation", "running"))
    assert (
        seq.index(("financial", "done")) < val_start and seq.index(("business", "done")) < val_start
    )


def test_valuation_reads_the_financial_and_business_findings_in_both_of_its_calls(mcp, monkeypatch):
    m = Models(monkeypatch)
    Coordinator(mcp).run_state("ACME")
    for kind in ("plan", "analysis"):
        (prompt,) = m.prompts("valuation", kind)
        assert (
            FIN_CLAIM in prompt
            and BIZ_CLAIM in prompt
            and "FIN-SUMMARY" in prompt
            and "BIZ-SUMMARY" in prompt
        )


def test_the_pair_still_never_sees_the_valuation_stage_or_each_other(mcp, monkeypatch):
    m = Models(monkeypatch)
    Coordinator(mcp).run_state("ACME")
    for agent in ("financial", "business"):
        (prompt,) = m.prompts(agent)
        assert "UPSTREAM" not in prompt and "CALCULATION RESULTS" not in prompt


def test_the_state_gets_valuation_and_expectations_claims_with_calc_values(mcp, monkeypatch):
    Models(
        monkeypatch,
        valuation=lambda n: val_analysis(
            vfinding("valuation"),
            vfinding(
                "expectations",
                ("reverse_dcf.implied_fcf_cagr",),
                ("fact:ACME:fcf:FY2025",),
                "The price implies faster free cash flow growth than management guides to.",
            ),
        ),
    )
    st = Coordinator(mcp).run_state("ACME")
    assert [c.claim_id.split(":")[1] for c in st.sections.valuation.claims] == ["valuation"]
    (expectation,) = st.sections.expectations.claims
    assert (
        expectation.value.value == pytest.approx(0.1161030155)
        and "fact:ACME:fcf:FY2025" in expectation.fact_ids
    )
    assert st.sections.valuation.owner is AgentName.VALUATION
    assert st.agent_outputs[AgentName.VALUATION].model_extra["valuation_plan"]["methods"]


def test_the_valuation_plan_travels_with_the_state_for_the_ui_and_the_record(mcp, monkeypatch):
    Models(monkeypatch)
    st = Coordinator(mcp).run_state("ACME")
    dumped = st.model_dump(mode="json")["agent_outputs"]["valuation"]["valuation_plan"]
    assert "pe" in dumped["methods"] and "reverse_dcf" in dumped["methods"] and dumped["peers"]


def test_the_report_renders_the_valuation_sections(mcp, monkeypatch):
    Models(monkeypatch)
    md = generator.render_markdown(Coordinator(mcp).run_state("ACME"))
    assert "## Valuation" in md and "premium to the peer median" in md


def test_a_calc_failure_fails_the_valuation_lane_and_the_run(mcp, monkeypatch):
    Models(monkeypatch)

    class Broken:
        def __init__(self, inner):
            self.inner = inner

        def call_tool(self, name, arguments):
            if name == "calculate_valuation":
                raise McpToolError(name, "calc/ is down")
            return self.inner.call_tool(name, arguments)

    run_id = events.new_run()
    with pytest.raises(McpToolError, match="calc/ is down"):
        Coordinator(Broken(mcp), run_id=run_id).run_state("ACME")
    seq = {(getattr(e.agent, "value", e.agent), e.status) for e in events.history(run_id)}
    assert ("valuation", "failed") in seq and ("financial", "done") in seq


def test_a_failed_valuation_claim_is_retried_with_the_gate_reasons(mcp, monkeypatch):
    from schema.contracts.verification import RetryDirective, VerificationIssue

    bad = "The shares trade at a premium to the peer median on trailing earnings."
    good = "The shares trade at a clear premium to the peer median."
    m = Models(
        monkeypatch, valuation=lambda n: val_analysis(vfinding(claim=bad if n == 1 else good))
    )

    def auditor(state, fs, get_text, verify_claim):
        sec = state["sections"]["valuation"]
        flagged = [c for c in sec["claims"] if c["text"] == bad]
        issues = [
            VerificationIssue(
                issue_type="unsupported_claim",
                severity="error",
                path="sections.valuation",
                message="the quote does not support the claim",
                claim_id=c["claim_id"],
                checked_by_llm=False,
            )
            for c in flagged
        ]
        directives = (
            [
                RetryDirective(
                    target_agent="valuation",
                    section_key="valuation",
                    issues=issues,
                    attempt=sec["retry_count"] + 1,
                )
            ]
            if issues and sec["retry_count"] < 2
            else []
        )
        n = sum(len(s["claims"]) for s in state["sections"].values())
        return {
            "schema_version": "2.0.0",
            "passed": not issues,
            "issues": [i.model_dump(mode="json") for i in issues],
            "claims_checked": n,
            "claims_verified": n - len(issues),
            "claims_unverified": len(issues),
            "llm_checks_run": 0,
            "retries_issued": [d.model_dump(mode="json") for d in directives],
        }

    st = Coordinator(
        mcp,
        auditor=auditor,
        factsheet=lambda ctx: json.loads(FACTSHEET.read_text()),
    ).run_state("ACME")
    assert [c.text for c in st.sections.valuation.claims] == [good]
    assert all(c.verification_status is VerificationStatus.VERIFIED for c in st.all_claims)
    retry_analysis = m.prompts("valuation")[1]
    assert (
        "VERIFICATION GATE REJECTED" in retry_analysis
        and "the quote does not support the claim" in retry_analysis
    )
    assert (
        len(m.prompts("valuation", "plan")) == 2 and len(m.prompts("financial")) == 1
    )  # only valuation re-ran
    assert FIN_CLAIM in retry_analysis  # upstream still visible on retry
