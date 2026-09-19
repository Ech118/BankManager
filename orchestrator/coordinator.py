"""The pipeline runner: plan, spawn, collect, route retries.

Specified by docs/pipeline.md.

    ingest (MCP)
      -> financial || business        [parallel]
      -> valuation
      -> scenario
      -> red_team
      -> calc.evaluate_scenarios      [weights bounded, prior capped]
      -> synthesizer
      -> audit.run_audit
           FAIL -> targeted retry of the owning agent, max 2
           PASS or cap reached -> failed claims marked unverified
      -> report generator

Three things this module is responsible for that are easy to get wrong:

  PARALLELISM. financial and business are independent and must actually run
  concurrently; wall-clock is otherwise the sum rather than the max, and the
  per-agent UI lanes have nothing to show.

  THE REDACT HOOK. Applied to ALL filing text before any agent sees it. Applied
  here, centrally, because an agent fetching its own section text could
  otherwise bypass anonymization and quietly contaminate a backtest (error A).

  THE RED TEAM'S INPUT. It gets the RAW fact sheet as well as the analyst
  outputs. Handing it only the summaries produces agreement in a sceptical tone
  (error J).

STATUS: Step 1 (roadmap). One agent (financial) runs sequentially against MCP and
produces a ResearchState. Parallelism, the remaining agents, verification and the
report are later steps and raise NotImplementedError with the step named.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from agents.base import Agent
from agents.financial_agent import FinancialAgent
from orchestrator import events
from orchestrator.mcp_client import McpToolError
from schema.contracts import SCHEMA_VERSION
from schema.contracts.common import DataQuality, ISODate, Ticker
from schema.contracts.enums import AgentName, Mode
from schema.contracts.state import SECTION_OWNERS, ResearchSection, ResearchSections, ResearchState
from schema.contracts.verdict import Verdict

log = logging.getLogger("bankmanager.coordinator")

SECTION_TITLES = {
    "company": "Company",
    "financials": "Financial quality",
    "balance_sheet": "Balance sheet strength",
    "cash_flow": "Free cash flow",
    "earnings_quality": "Earnings quality",
    "management": "Management and guidance",
    "competitive_position": "Competitive position",
    "valuation": "Valuation",
    "expectations": "Expectations vs reality",
    "catalysts": "Catalysts",
    "risks": "Risks",
    "scenarios": "Bull / base / bear",
    "sp500_comparison": "S&P 500 comparison",
    "decision": "Investment committee decision",
}

IMPLEMENTED: dict[AgentName, type[Agent]] = {AgentName.FINANCIAL: FinancialAgent}
"""Agents that exist so far. Grows with the roadmap; `plan()` reads it."""

CANONICAL_ORDER = [
    AgentName.FINANCIAL,
    AgentName.BUSINESS,
    AgentName.VALUATION,
    AgentName.SCENARIO,
    AgentName.RED_TEAM,
    AgentName.SYNTHESIZER,
]
PARALLEL_PAIR = (AgentName.FINANCIAL, AgentName.BUSINESS)

FACT_METRICS = [
    "revenue",
    "cost_of_revenue",
    "gross_profit",
    "operating_income",
    "pretax_income",
    "net_income",
    "eps_diluted",
    "shares_diluted",
    "depreciation_amortization",
    "op_cash_flow",
    "capex",
    "sbc",
    "cash",
    "total_debt",
    "interest_expense",
    "total_assets",
    "total_equity",
    "current_assets",
    "current_liabilities",
    "receivables",
    "inventory",
]
SECTION_ITEMS = ("mdna", "sbc_note", "debt_note")
"""Filing items the Financial Agent reads. Sections, not whole filings (error K)."""
MAX_SECTION_CHARS = 60_000


def today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def current_mode() -> Mode:
    return Mode(os.environ.get("MODE", os.environ.get("BM_MODE", "mock")).lower())


def new_state(
    ticker: str, as_of: str, mode: Mode, redacted: bool, data_quality: DataQuality
) -> ResearchState:
    """An empty ResearchState: all fourteen sections present, owners from SECTION_OWNERS."""
    sections = ResearchSections(
        **{
            key: ResearchSection(section_key=key, title=SECTION_TITLES[key], owner=owner)
            for key, owner in SECTION_OWNERS.items()
        }
    )
    return ResearchState(
        schema_version=SCHEMA_VERSION,
        ticker=ticker,
        as_of=as_of,
        created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        mode=mode,
        sections=sections,
        data_quality=data_quality,
        redacted=redacted,
    )


class Coordinator:
    """Runs one analysis end to end."""

    def __init__(
        self,
        mcp: Any,
        redact: Callable[[str], str] | None = None,
        run_id: str | None = None,
        mode: Mode | None = None,
    ) -> None:
        self.mcp = mcp
        self.redact = redact
        self.run_id = run_id or "local"
        self.mode = mode or current_mode()
        self.stats: dict[str, Any] = {"agents": {}}

    # ----------------------------------------------------------------- helpers
    def _emit(self, agent: AgentName | str, status: str, **kw: Any) -> None:
        events.emit(events.AgentEvent(run_id=self.run_id, agent=agent, status=status, **kw))

    def plan(self, ticker: Ticker, as_of: ISODate | None) -> list[str]:
        """Agent execution order, honouring the parallel pair (financial || business)."""
        return [a.value for a in CANONICAL_ORDER if a in IMPLEMENTED]

    # ------------------------------------------------------------------ ingest
    def ingest(self, ticker: Ticker, as_of: ISODate | None) -> dict:
        """Fetch facts and filing sections through MCP.

        Scope is enforced by the data tools: an out-of-scope ticker makes them
        raise, and that reason is re-raised here as ValueError BEFORE any model
        call (a refusal costs nothing).
        """
        as_of = as_of or today()
        self._emit("ingest", "running")
        try:
            profile = self.mcp.call_tool("get_company_profile", {"ticker": ticker, "as_of": as_of})[
                "profile"
            ]
            if profile is None:
                raise ValueError(f"{ticker}: no company profile available as of {as_of}")
            facts = self.mcp.call_tool(
                "get_financial_facts", {"ticker": ticker, "metrics": FACT_METRICS, "as_of": as_of}
            )["facts"]
            filings = self.mcp.call_tool(
                "search_filings", {"ticker": ticker, "as_of": as_of, "forms": ["10-K", "10-Q"]}
            )["filings"]
        except McpToolError as e:
            self._emit("ingest", "failed", detail=e.detail)
            raise ValueError(e.detail) from e
        gaps: list[str] = []
        sections: list[dict] = []
        wanted = set(SECTION_ITEMS)
        for (
            filing
        ) in filings:  # newest first: take each item from the most recent filing that has it
            for section_id in filing["section_ids"]:
                item = section_id.rsplit(":", 1)[-1]
                if item not in wanted:
                    continue
                try:
                    sec = self.mcp.call_tool(
                        "get_filing_section",
                        {"section_id": section_id, "as_of": as_of, "max_chars": MAX_SECTION_CHARS},
                    )["section"]
                except McpToolError as e:
                    gaps.append(f"Filing section {section_id} unavailable: {e.detail}")
                    continue
                if sec:
                    sections.append(sec)
                    wanted.discard(item)
        for item in sorted(wanted):
            gaps.append(f"No {item} section found in the filings available as of {as_of}")
        if not facts:
            gaps.append("No financial facts available")
        self._emit("ingest", "done")
        return {
            "ticker": ticker,
            "as_of": as_of,
            "profile": profile,
            "facts": facts,
            "sections": sections,
            "filings": filings,
            "gaps": gaps,
        }

    # ----------------------------------------------------------------- agents
    def run_agents(self, state: ResearchState, context: dict) -> ResearchState:
        """Run the implemented roster in order. Step 1: sequential, one agent.

        TODO(roadmap Step 3, P3): run financial and business concurrently.
        """
        for name in CANONICAL_ORDER:
            cls = IMPLEMENTED.get(name)
            if cls is None:
                continue
            agent = cls(self.mcp, redact=self.redact)
            self._emit(name, "running")
            t0 = time.monotonic()
            try:
                analysis = agent.run(context)
            except Exception as e:
                self._emit(name, "failed", detail=str(e))
                raise
            claims = agent.to_claims(analysis)
            for claim in claims:
                key = (claim.model_extra or {}).get("section_key") or agent.sections[0]
                getattr(state.sections, key).claims.append(claim)
            state.agent_outputs[name] = analysis
            if agent.guard_flags:
                state.data_quality.gaps += [
                    f"Possible prompt-injection text removed from {f.source_id}: {f.snippet!r}"
                    for f in agent.guard_flags
                ]
                if state.data_quality.overall == "ok":
                    state.data_quality.overall = "partial"
                self._emit(
                    "guard",
                    "flagged",
                    detail=f"{len(agent.guard_flags)} instruction-like sentence(s) removed",
                )
            self.stats["agents"][name.value] = {
                **agent.usage,
                "dropped": agent.dropped,
                "claims": len(claims),
                "wall_seconds": round(time.monotonic() - t0, 3),
            }
            self._emit(
                name,
                "done",
                tokens_in=agent.usage["tokens_in"],
                tokens_out=agent.usage["tokens_out"],
            )
        return state

    def verify(self, state: ResearchState, context: dict) -> ResearchState:
        """Audit, route retries to section owners, stop at the cap.

        After the cap the run CONTINUES with the failing claims marked
        unverified. Blocking the report would trade a visible flaw for an
        invisible one (ADR 0005).
        """
        raise NotImplementedError("TODO(roadmap Step 5, P3)")

    # -------------------------------------------------------------------- run
    def run_state(self, ticker: Ticker, as_of: ISODate | None = None) -> ResearchState:
        """Ingest, run the agents, return the ResearchState (the Step 1 checkpoint)."""
        t0 = time.monotonic()
        context = self.ingest(ticker, as_of)
        quality = DataQuality(
            overall="partial" if context["gaps"] else "ok", gaps=list(context["gaps"])
        )
        state = new_state(ticker, context["as_of"], self.mode, self.redact is not None, quality)
        state = self.run_agents(state, context)
        state = ResearchState.model_validate(
            state.model_dump(mode="json")
        )  # re-run every contract validator
        self.stats.update(
            {
                "ticker": ticker,
                "as_of": context["as_of"],
                "seconds": round(time.monotonic() - t0, 3),
                "tokens_in": sum(a["tokens_in"] for a in self.stats["agents"].values()),
                "tokens_out": sum(a["tokens_out"] for a in self.stats["agents"].values()),
            }
        )
        events.log_run(self.stats)
        return state

    def run(self, ticker: Ticker, as_of: ISODate | None = None) -> Verdict:
        """The whole pipeline.

        TODO(roadmap Step 2, P3): render the Verdict from the ResearchState.
        """
        raise NotImplementedError("TODO(roadmap Step 2, P3): report generator")
