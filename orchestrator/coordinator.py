"""The pipeline runner: plan, spawn, collect, route retries.

Specified by docs/pipeline.md.

    ingest (code)
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

TODO(roadmap Step 1, P3): sequential mock run with one agent.
TODO(roadmap Step 3, P3): parallel execution.
TODO(roadmap Step 5, P3): red team, synthesizer, retry loop.
"""

from __future__ import annotations

from collections.abc import Callable

from schema.contracts.common import ISODate, Ticker
from schema.contracts.state import ResearchState
from schema.contracts.verdict import Verdict


class Coordinator:
    """Runs one analysis end to end."""

    def __init__(self, mcp: object, redact: Callable[[str], str] | None = None) -> None:
        self.mcp = mcp
        self.redact = redact
        raise NotImplementedError("TODO(roadmap Step 1, P3)")

    def plan(self, ticker: Ticker, as_of: ISODate | None) -> list[str]:
        """Agent execution order, honouring the parallel pair."""
        raise NotImplementedError("TODO(roadmap Step 1, P3)")

    def ingest(self, ticker: Ticker, as_of: ISODate | None) -> dict:
        """Fetch the fact sheet and metrics through MCP, then check scope.

        check_scope runs FIRST: an out-of-scope company should cost nothing and
        produce a clear refusal, not a confident-looking analysis.
        """
        raise NotImplementedError("TODO(roadmap Step 1, P3)")

    def run_agents(self, state: ResearchState, context: dict) -> ResearchState:
        """Run the roster in order, financial and business concurrently."""
        raise NotImplementedError("TODO(roadmap Step 3, P3)")

    def verify(self, state: ResearchState, context: dict) -> ResearchState:
        """Audit, route retries to section owners, stop at the cap.

        After the cap the run CONTINUES with the failing claims marked
        unverified. Blocking the report would trade a visible flaw for an
        invisible one (ADR 0005).
        """
        raise NotImplementedError("TODO(roadmap Step 5, P3)")

    def run(self, ticker: Ticker, as_of: ISODate | None = None) -> Verdict:
        """The whole pipeline."""
        raise NotImplementedError("TODO(roadmap Step 1, P3)")
