"""Step 3: the financial/business pair run concurrently, independently, and merge deterministically."""

import json
import threading
import time

import pytest

from agents import client
from agents.tests.helpers import DEFAULT_PLAN, MDNA_ID, analysis_payload, finding
from orchestrator import events
from orchestrator.coordinator import Coordinator
from orchestrator.mcp_client import InMemoryMcpClient
from tests.e2e.support.fake_mcp import build_fake_server

BUSINESS_ID = "src:edgar:0001234567-26-000010:business"


@pytest.fixture()
def mcp():
    c = InMemoryMcpClient(build_fake_server())
    yield c
    c.close()


def install(monkeypatch, per_agent):
    """Replace client.complete. per_agent: {agent_value: callable(system, user) -> dict|str}."""
    calls = []
    lock = threading.Lock()

    def fake(agent, system, user, max_tokens=4096, schema=None, kind="analysis"):
        with lock:
            calls.append({"agent": agent.value, "system": system, "user": user, "kind": kind})
        if kind == "plan":
            out = DEFAULT_PLAN
        else:
            out = per_agent.get(agent.value, lambda s, u: fin())(system, user)
        text = out if isinstance(out, str) else json.dumps(out)
        return {"text": text, "model": "test", "tokens_in": 10, "tokens_out": 5, "seconds": 0.0}

    monkeypatch.setattr(client, "complete", fake)
    return calls


def fin(summary="fin"):
    return analysis_payload(finding(section="financials"), summary=summary)


def biz(summary="biz"):
    return analysis_payload(
        finding(
            claim="Customers renew at a high rate.",
            quote="renewed at a rate of 94%",
            source_id=BUSINESS_ID,
            fact_ids=(),
            section="competitive_position",
        ),
        summary=summary,
    )


def test_financial_and_business_agents_run_concurrently(mcp, monkeypatch):
    """A barrier that only opens when BOTH model calls are in flight at the same time."""
    barrier = threading.Barrier(2, timeout=5)

    def gated(payload):
        def call(system, user):
            barrier.wait()  # a sequential run would time out here and fail the test
            return payload

        return call

    install(monkeypatch, {"financial": gated(fin()), "business": gated(biz())})
    state = Coordinator(mcp).run_state("ACME")
    assert {a.value for a in state.agent_outputs} == {"financial", "business", "valuation"}


def test_both_lanes_are_running_before_either_finishes(mcp, monkeypatch):
    barrier = threading.Barrier(2, timeout=5)

    def gated(payload):
        return lambda system, user: (barrier.wait(), payload)[1]

    install(monkeypatch, {"financial": gated(fin()), "business": gated(biz())})
    run_id = events.new_run()
    Coordinator(mcp, run_id=run_id).run_state("ACME")
    seq = [(getattr(e.agent, "value", e.agent), e.status) for e in events.history(run_id)]
    first_done = next(
        i for i, (_, s) in enumerate(seq) if s == "done" and _ in ("financial", "business")
    )
    running = {a for a, s in seq[:first_done] if s == "running"}
    assert {"financial", "business"} <= running


def test_merge_order_does_not_depend_on_which_agent_finishes_first(mcp, monkeypatch):
    def slow(payload, seconds):
        def call(system, user):
            time.sleep(seconds)
            return payload

        return call

    def claim_order(fin_delay, biz_delay):
        install(
            monkeypatch, {"financial": slow(fin(), fin_delay), "business": slow(biz(), biz_delay)}
        )
        st = Coordinator(mcp).run_state("ACME")
        return [c.claim_id for c in st.all_claims], list(st.agent_outputs)

    assert claim_order(0.15, 0.0) == claim_order(0.0, 0.15)


def test_neither_agent_sees_the_other(mcp, monkeypatch):
    calls = install(
        monkeypatch,
        {
            "financial": lambda s, u: fin("FINANCIAL-SENTINEL"),
            "business": lambda s, u: biz("BUSINESS-SENTINEL"),
        },
    )
    Coordinator(mcp).run_state("ACME")
    prompts = {c["agent"]: c["system"] + c["user"] for c in calls}
    assert (
        "BUSINESS-SENTINEL" not in prompts["financial"]
        and "FINANCIAL-SENTINEL" not in prompts["business"]
    )


def test_each_agent_is_shown_only_its_own_filing_items(mcp, monkeypatch):
    calls = install(monkeypatch, {"financial": lambda s, u: fin(), "business": lambda s, u: biz()})
    Coordinator(mcp).run_state("ACME")
    prompts = {c["agent"]: c["user"] for c in calls}
    assert ":sbc_note" in prompts["financial"] and ":debt_note" in prompts["financial"]
    assert ":business" not in prompts["financial"] and ":risk_factors" not in prompts["financial"]
    assert ":business" in prompts["business"] and ":risk_factors" in prompts["business"]
    assert ":sbc_note" not in prompts["business"] and ":debt_note" not in prompts["business"]
    assert (
        f'source_id="{MDNA_ID}"' in prompts["financial"]
        and f'source_id="{MDNA_ID}"' in prompts["business"]
    )


def test_one_agent_failing_still_lets_the_other_finish_and_reports_both(mcp, monkeypatch):
    install(
        monkeypatch, {"financial": lambda s, u: fin(), "business": lambda s, u: "not json at all"}
    )
    run_id = events.new_run()
    with pytest.raises(Exception, match="business: invalid output"):
        Coordinator(mcp, run_id=run_id).run_state("ACME")
    seq = {(getattr(e.agent, "value", e.agent), e.status) for e in events.history(run_id)}
    assert ("financial", "done") in seq and ("business", "failed") in seq  # no orphaned lane


def test_the_first_failure_in_canonical_order_is_the_one_raised(mcp, monkeypatch):
    install(monkeypatch, {"financial": lambda s, u: "bad", "business": lambda s, u: "also bad"})
    with pytest.raises(Exception, match="financial: invalid output"):
        Coordinator(mcp).run_state("ACME")


def test_stages_group_the_pair_and_keep_the_rest_sequential():
    stages = [[a.value for a in stage] for stage in Coordinator.stages()]
    assert stages[0] == ["financial", "business"] and all(len(s) == 1 for s in stages[1:])


def test_business_claims_land_in_business_sections_and_financial_in_financial(mcp, monkeypatch):
    install(monkeypatch, {"financial": lambda s, u: fin(), "business": lambda s, u: biz()})
    st = Coordinator(mcp).run_state("ACME")
    assert [c.claim_id.split(":")[1] for c in st.sections.competitive_position.claims] == [
        "business"
    ]
    assert [c.claim_id.split(":")[1] for c in st.sections.financials.claims] == ["financial"]
    assert st.sections.competitive_position.owner.value == "business"
