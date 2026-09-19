"""The retry loop (ADR 0005): targeted, capped at two, ships with failures marked, never hides a claim."""

import json
from pathlib import Path

import pytest

from agents import client
from agents.tests.helpers import DEFAULT_PLAN, analysis_payload, finding
from orchestrator import events
from orchestrator.coordinator import Coordinator
from orchestrator.mcp_client import InMemoryMcpClient
from orchestrator.report import generator
from schema.contracts.enums import AgentName, VerificationStatus
from tests.e2e.support.fake_mcp import build_fake_server

MOCK = Path(__file__).resolve().parents[2] / "fixtures" / "mock"
BUSINESS_ID = "src:edgar:0001234567-26-000010:business"


@pytest.fixture()
def mcp():
    c = InMemoryMcpClient(build_fake_server())
    yield c
    c.close()


def payload(agent, claim="Gross margin expanded on price and mix."):
    if agent == "business":
        return analysis_payload(
            finding(
                claim="Customers renew at a high rate.",
                quote="renewed at a rate of 94%",
                source_id=BUSINESS_ID,
                fact_ids=(),
                section="competitive_position",
            )
        )
    return analysis_payload(finding(claim=claim, section="financials"))


class Model:
    """Scripted model that records prompts and lets a test change what the financial agent says on a retry."""

    def __init__(self, monkeypatch, financial=None):
        self.calls = []
        self.financial = financial or (lambda n: payload("financial"))
        monkeypatch.setattr(client, "complete", self)

    def __call__(self, agent, system, user, max_tokens=4096, schema=None, kind="analysis"):
        self.calls.append({"agent": agent.value, "user": user, "kind": kind})
        n = sum(1 for c in self.calls if c["agent"] == agent.value and c["kind"] == kind)
        if kind == "plan":
            out = DEFAULT_PLAN
        else:
            out = self.financial(n) if agent.value == "financial" else payload(agent.value)
        return {
            "text": json.dumps(out),
            "model": "t",
            "tokens_in": 10,
            "tokens_out": 5,
            "seconds": 0.0,
        }

    def count(self, agent):
        return sum(1 for c in self.calls if c["agent"] == agent)


def factsheet(context):
    return json.loads((MOCK / "factsheet.json").read_text())


def make_auditor(fail_when, retryable=True, seen=None):
    """A P2-like auditor: flags financial `financials` claims for which fail_when(claim_text) is true,
    issues a directive while the section has attempts left (it reads section.retry_count)."""
    from schema.contracts.verification import RetryDirective, VerificationIssue

    def auditor(state, fs, get_text, verify_claim):
        if seen is not None:
            seen.append(json.loads(json.dumps(state["sections"]["financials"])))
        issues, directives = [], []
        sec = state["sections"]["financials"]
        bad = [c for c in sec["claims"] if fail_when(c["text"])]
        for c in bad:
            issues.append(
                VerificationIssue(
                    issue_type="unsupported_claim" if retryable else "future_fact",
                    severity="error",
                    path="sections.financials",
                    message="the quote does not support the claim",
                    claim_id=c["claim_id"],
                    expected="a supported claim",
                    actual=c["text"],
                    checked_by_llm=False,
                )
            )
        attempt = sec["retry_count"] + 1
        if bad and retryable and attempt <= 2:
            directives.append(
                RetryDirective(
                    target_agent="financial",
                    section_key="financials",
                    issues=issues,
                    attempt=attempt,
                )
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

    return auditor


def run(mcp, auditor, run_id=None):
    coord = Coordinator(mcp, auditor=auditor, factsheet=factsheet, run_id=run_id or "r")
    return coord, coord.run_state("ACME")


BAD = "Gross margin expanded on price and mix."
GOOD = "Gross margin expanded because software mix rose."


def test_a_failing_section_is_retried_once_with_the_reasons_and_then_passes(mcp, monkeypatch):
    model = Model(monkeypatch, financial=lambda n: payload("financial", BAD if n == 1 else GOOD))
    _, st = run(mcp, make_auditor(lambda text: text == BAD))
    assert (
        model.count("financial") == 2 and model.count("business") == 1
    )  # targeted: business NOT re-run
    retry_prompt = [c for c in model.calls if c["agent"] == "financial"][1]["user"]
    assert (
        "VERIFICATION GATE REJECTED" in retry_prompt
        and "the quote does not support the claim" in retry_prompt
    )
    assert f'claim: "{BAD}"' in retry_prompt and "attempt 1 of 2" in retry_prompt
    assert (
        st.sections.financials.retry_count == 1
        and st.sections.competitive_position.retry_count == 0
    )
    assert [c.text for c in st.sections.financials.claims] == [GOOD]
    assert all(c.verification_status is VerificationStatus.VERIFIED for c in st.all_claims)
    assert st.verification.passed


def test_only_the_failing_section_changes_and_claim_ids_stay_unique(mcp, monkeypatch):
    Model(monkeypatch, financial=lambda n: payload("financial", BAD if n == 1 else GOOD))
    _, st = run(mcp, make_auditor(lambda text: text == BAD))
    ids = [c.claim_id for c in st.all_claims]
    assert len(ids) == len(set(ids))
    assert any(":r1-" in i for i in ids)  # the replacement carries its attempt
    assert [c.text for c in st.sections.competitive_position.claims] == [
        "Customers renew at a high rate."
    ]


def test_the_cap_is_two_then_the_report_ships_with_the_claim_marked(mcp, monkeypatch):
    model = Model(monkeypatch)  # the agent never fixes it
    _, st = run(mcp, make_auditor(lambda text: text == BAD))
    assert model.count("financial") == 3  # first pass + exactly two retries
    assert st.sections.financials.retry_count == 2
    marked = [c for c in st.all_claims if c.verification_status is VerificationStatus.UNVERIFIED]
    assert [c.text for c in marked] == [BAD]
    assert st.sections.financials.verification_status is VerificationStatus.UNVERIFIED
    md = generator.render_section(st.sections.financials).body_markdown
    assert BAD in md and "**[UNVERIFIED]**" in md  # rendered and labelled, never dropped


def test_a_non_retryable_failure_costs_no_extra_model_call(mcp, monkeypatch):
    model = Model(monkeypatch)
    _, st = run(mcp, make_auditor(lambda text: text == BAD, retryable=False))
    assert model.count("financial") == 1  # future_fact: escalate, don't re-prompt
    assert st.sections.financials.retry_count == 0
    assert any(c.verification_status is VerificationStatus.UNVERIFIED for c in st.all_claims)


def test_a_retry_that_returns_nothing_keeps_the_original_claims_rather_than_dropping_them(
    mcp, monkeypatch
):
    def financial(n):
        if n == 1:
            return payload("financial", BAD)
        return analysis_payload(
            finding(claim="Elsewhere.", section="earnings_quality")
        )  # nothing for `financials`

    Model(monkeypatch, financial=financial)
    _, st = run(mcp, make_auditor(lambda text: text == BAD))
    assert BAD in [c.text for c in st.sections.financials.claims]  # still there
    assert any(
        c.text == BAD and c.verification_status is VerificationStatus.UNVERIFIED
        for c in st.all_claims
    )


def test_the_retry_shows_as_a_retrying_lane_event(mcp, monkeypatch):
    Model(monkeypatch, financial=lambda n: payload("financial", BAD if n == 1 else GOOD))
    run_id = events.new_run()
    run(mcp, make_auditor(lambda text: text == BAD), run_id=run_id)
    retrying = [e for e in events.history(run_id) if e.status == "retrying"]
    assert len(retrying) == 1 and retrying[0].agent is AgentName.FINANCIAL
    assert "financials" in retrying[0].detail and "attempt 1 of 2" in retrying[0].detail


def test_retry_tokens_are_counted_in_the_run_stats(mcp, monkeypatch):
    Model(monkeypatch, financial=lambda n: payload("financial", BAD if n == 1 else GOOD))
    coord, _ = run(mcp, make_auditor(lambda text: text == BAD))
    assert coord.stats["agents"]["financial"]["retries"] == 1
    assert coord.stats["agents"]["financial"]["tokens_in"] == 20  # first pass + one retry


def test_the_auditor_sees_the_state_after_each_retry(mcp, monkeypatch):
    Model(monkeypatch, financial=lambda n: payload("financial", BAD if n == 1 else GOOD))
    seen = []
    run(mcp, make_auditor(lambda text: text == BAD, seen=seen))
    assert [s["retry_count"] for s in seen] == [0, 1]  # audited before, then after the retry
    assert seen[1]["claims"][0]["text"] == GOOD


def test_a_directive_for_an_unbuilt_agent_leaves_the_claims_marked_not_lost(mcp, monkeypatch):
    from orchestrator import retry

    Model(monkeypatch)
    coord, st = run(mcp, make_auditor(lambda text: False))
    rerun = coord._rerun({})
    assert rerun(AgentName.RED_TEAM, ["x"], "r1-") == []  # nothing to run: no crash, no claims
    assert retry.MAX_ATTEMPTS == 2
