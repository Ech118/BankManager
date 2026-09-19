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
