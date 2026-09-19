"""Roadmap checkpoints for P3 (docs/roadmap.md). Each test decides whether a step is met."""

import sys

from orchestrator.coordinator import Coordinator
from orchestrator.mcp_client import InMemoryMcpClient, StdioMcpClient
from schema.contracts.enums import AgentName
from schema.contracts.state import SECTION_OWNERS, ResearchState
from tests.e2e.support.fake_mcp import build_fake_server


def _assert_step1(state: ResearchState) -> None:
    ResearchState.model_validate(state.model_dump(mode="json"))
    owned = {k for k, o in SECTION_OWNERS.items() if o is AgentName.FINANCIAL}
    filled = {s.section_key for s in state.sections.as_list() if s.claims}
    assert filled and filled <= owned  # the financial agent's sections, and nothing else
    assert set(state.agent_outputs) == {AgentName.FINANCIAL}
    assert state.data_quality.overall == "ok" and state.ticker == "ACME"


def test_mock_run_produces_a_research_state_with_one_section():
    """Step 1 checkpoint: coordinator + real MCP (in-memory) + one agent."""
    mcp = InMemoryMcpClient(build_fake_server())
    try:
        _assert_step1(Coordinator(mcp).run_state("ACME"))
    finally:
        mcp.close()


def test_the_same_run_works_over_the_stdio_transport():
    """Live mode's transport: the identical pipeline through a spawned MCP server process."""
    mcp = StdioMcpClient([sys.executable, "-m", "tests.e2e.support.fake_mcp"])
    try:
        _assert_step1(Coordinator(mcp).run_state("ACME"))
    finally:
        mcp.close()


# ---------------------------------------------------------------------- Step 2 checkpoint
import json  # noqa: E402
import re  # noqa: E402
from pathlib import Path  # noqa: E402

from orchestrator.report import generator  # noqa: E402
from schema.contracts.verdict import Verdict  # noqa: E402

_MOCK = Path(__file__).resolve().parents[2] / "fixtures" / "mock"


def _acme_state() -> ResearchState:
    """The frozen ACME ResearchState with the extras the Coordinator adds (company, market, synthesis)."""
    d = json.loads((_MOCK / "research_state.json").read_text())
    card = json.loads((_MOCK / "verdict.json").read_text())
    d["company_name"] = card["card"]["company"]
    d["market"] = json.loads((_MOCK / "market_snapshot.json").read_text())
    d["synthesis"] = {
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
    return ResearchState.model_validate(d)


def test_acme_full_mock_report_has_every_number_resolving():
    """Step 2 checkpoint: every number in the report traces to a fact_id, and every fact_id resolves.

    Resolution goes through the real MCP protocol (resolve_fact), not around it.
    """
    state = _acme_state()
    verdict = generator.render(state)
    Verdict.model_validate(verdict.model_dump(mode="json"))
    mcp = InMemoryMcpClient(build_fake_server())
    try:
        for claim in state.all_claims:
            if claim.has_number:  # value, or a numeral in the prose
                assert claim.fact_ids or claim.unsourced_numbers == [], (
                    f"{claim.claim_id}: bare number"
                )
            for fact_id in claim.fact_ids:
                out = mcp.call_tool("resolve_fact", {"fact_id": fact_id, "as_of": state.as_of})
                assert out["fact"] is not None, f"{claim.claim_id}: {fact_id} does not resolve"
                assert not out["is_future"], f"{fact_id} is from after the run's as_of"
    finally:
        mcp.close()
    # the rendered text cites the same ids, so a reader can follow every number to its fact
    md = generator.render_markdown(state, verdict)
    cited = {fid for c in state.all_claims for fid in c.fact_ids}
    assert cited and all(fid in md for fid in cited)
    assert not re.search(r"\(0\.0%|\$0 ", md)  # no fabricated zeros


def test_disclaimer_present_in_every_rendered_report():
    """Error M: the full report, the preliminary report and the Verdict object all carry it."""
    state = _acme_state()
    verdict = generator.render(state)
    assert verdict.disclaimer == generator.DISCLAIMER
    assert generator.render_markdown(state, verdict).count(generator.DISCLAIMER) == 2
    assert generator.render_markdown(state).count(generator.DISCLAIMER) == 2
