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

STATUS: Step 2 (roadmap). One agent (financial) runs sequentially against MCP and
produces a ResearchState; `verify()` runs the injected auditor once and marks
claims; `orchestrator/report/` renders the report. Parallelism, the remaining
agents and the retry loop are later steps and say so.

THE AUDITOR IS INJECTED. P3 may not import audit/ (ADR 0007), so whoever composes
the process passes `auditor` (audit.api.run_audit), `factsheet` (a provider that
returns the Factsheet dict audit needs) and optionally `verify_claim`. Nothing on
the MCP surface yields a Factsheet today, so the composition root has to supply
it (docs/requests/2026-09-19-p3-report-inputs.md).
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from agents.base import Agent, section_id_for
from agents.financial_agent import FinancialAgent
from orchestrator import events
from orchestrator.mcp_client import McpToolError
from schema.contracts import SCHEMA_VERSION
from schema.contracts.common import DataQuality, ISODate, Ticker
from schema.contracts.enums import AgentName, Mode, Severity, VerificationStatus
from schema.contracts.state import SECTION_OWNERS, ResearchSection, ResearchSections, ResearchState
from schema.contracts.verdict import Verdict
from schema.contracts.verification import VerificationResult

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
    ticker: str, as_of: str, mode: Mode, redacted: bool, data_quality: DataQuality, **extras: Any
) -> ResearchState:
    """An empty ResearchState: all fourteen sections present, owners from SECTION_OWNERS.

    `extras` land in the state's extra="allow" space (company_name, market, synthesis...): the
    report is a pure function of the state, so anything it needs must live on it."""
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
        **extras,
    )


class VerifierUnavailable(RuntimeError):
    """verify() was asked for but no auditor or factsheet was injected."""


class Coordinator:
    """Runs one analysis end to end."""

    def __init__(
        self,
        mcp: Any,
        redact: Callable[[str], str] | None = None,
        run_id: str | None = None,
        mode: Mode | None = None,
        auditor: Callable[..., dict] | None = None,
        factsheet: Callable[[dict], dict] | None = None,
        verify_claim: Callable[[str, str], bool] | None = None,
    ) -> None:
        self.mcp = mcp
        self.redact = redact
        self.auditor = auditor
        self.factsheet = factsheet
        self.verify_claim = verify_claim
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
            market = self.mcp.call_tool("get_market_snapshot", {"ticker": ticker, "as_of": as_of})[
                "snapshot"
            ]
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
        if market is None:
            gaps.append("No market snapshot available: price and market cap are unavailable")
        self._emit("ingest", "done")
        return {
            "ticker": ticker,
            "as_of": as_of,
            "profile": profile,
            "facts": facts,
            "market": market,
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
        """Run the injected auditor once and mark every claim verified or failed.

        Step 2: a single pass. Failed claims stay `failed` and render with the
        UNVERIFIED marker. TODO(roadmap Step 5, P3): route RetryDirectives to the owning
        agent, max 2 attempts, then ship the failures marked `unverified` (ADR 0005).
        """
        if self.auditor is None or self.factsheet is None:
            raise VerifierUnavailable(
                "verify() needs an injected `auditor` and `factsheet` provider; P3 may not import "
                "audit/ or data/ itself (see docs/requests/2026-09-19-p3-report-inputs.md)"
            )
        self._emit("verify", "running")

        def get_text(source_id: str) -> str:
            section_id = section_id_for(source_id)
            if section_id is None:
                raise KeyError(source_id)
            try:
                text = self.mcp.call_tool(
                    "get_filing_section", {"section_id": section_id, "as_of": state.as_of}
                )["section"]["text"]
            except McpToolError as e:
                raise KeyError(source_id) from e
            return self.redact(text) if self.redact else text

        try:
            raw = self.auditor(
                state.model_dump(mode="json"), self.factsheet(context), get_text, self.verify_claim
            )
            result = VerificationResult.model_validate(raw)
        except Exception as e:
            self._emit("verify", "failed", detail=str(e))
            raise
        state.verification = result
        failed = {i.claim_id for i in result.issues if i.claim_id and i.severity is Severity.ERROR}
        for section in state.sections.as_list():
            for claim in section.claims:
                claim.verification_status = (
                    VerificationStatus.FAILED
                    if claim.claim_id in failed
                    else VerificationStatus.VERIFIED
                )
            if section.claims:
                section.verification_status = (
                    VerificationStatus.FAILED
                    if any(c.claim_id in failed for c in section.claims)
                    else VerificationStatus.VERIFIED
                )
        self._emit(
            "verify", "done", detail=f"{result.claims_verified}/{result.claims_checked} verified"
        )
        return state

    # -------------------------------------------------------------------- run
    def run_state(self, ticker: Ticker, as_of: ISODate | None = None) -> ResearchState:
        """Ingest, run the agents, return the ResearchState (the Step 1 checkpoint)."""
        t0 = time.monotonic()
        context = self.ingest(ticker, as_of)
        quality = DataQuality(
            overall="partial" if context["gaps"] else "ok", gaps=list(context["gaps"])
        )
        state = new_state(
            ticker,
            context["as_of"],
            self.mode,
            self.redact is not None,
            quality,
            company_name=context["profile"]["company_name"],
            market=context["market"],
        )
        state = self.run_agents(state, context)
        if self.auditor is not None and self.factsheet is not None:
            state = self.verify(state, context)
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

        TODO(roadmap Step 5, P3): needs the scenario agent, red team, synthesizer and calc's
        evaluate_scenarios before a Verdict can exist. Until then `run_state()` plus
        `report.render_markdown()` gives a preliminary report that shows no verdict.
        """
        raise NotImplementedError("TODO(roadmap Step 5, P3): scenario, red team, synthesizer")
