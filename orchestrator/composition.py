"""The composition root: the real MCP server, the real calc/ and the real audit/.

P3 may not import `mcp_server/`, `calc/` or `audit/` (ADR 0007), so somebody has
to, once, at the edge of the process. That is this file - the only place in the
pipeline that imports all three, and it holds no logic beyond wiring. The
Coordinator still receives everything as injected ports, so nothing below it
knows where these objects came from.

    from orchestrator.composition import real_composition
    real_composition()                       # configures orchestrator.server
    verdict = orchestrator.api.run_analysis("AAPL")

`tests/e2e/support/fake_calc.py` and `fake_mcp.py` stay exactly as they are: the
unit tests keep using them, and this file is what production uses instead.
"""

from __future__ import annotations

import os
from typing import Any


def mode() -> str:
    return os.environ.get("MODE", os.environ.get("BM_MODE", "mock")).lower()


class CalcPort:
    """The three calls the Coordinator makes, forwarded to `calc.api`.

    It also remembers the last `Metrics` it computed, so the factsheet provider can
    hand `audit/` the factsheet WITH calc's derived facts attached. Without that the
    verifier cannot resolve a fact_id that calc/ minted, and every computed number a
    claim cites would look unresolved.
    """

    def __init__(self) -> None:
        from calc import api as calc_api

        self._calc = calc_api
        self.last_metrics: dict | None = None

    def compute_metrics(self, factsheet: dict) -> dict:
        self.last_metrics = self._calc.compute_metrics(factsheet)
        return self.last_metrics

    def evaluate_scenarios(
        self, scenarios: dict, factsheet: dict, metrics: dict, prior_shifts: Any = None
    ) -> dict:
        return self._calc.evaluate_scenarios(scenarios, factsheet, metrics, prior_shifts)

    def derive_scores(self, scenario_result: dict) -> dict:
        return self._calc.derive_scores(scenario_result)

    def validate_consistency(self, scenario_result: dict, verdict_card: dict) -> dict:
        return self._calc.validate_consistency(scenario_result, verdict_card)


def build_mcp_server() -> Any:
    """The real MCP server object, for the SDK's in-memory transport."""
    from mcp_server.server import build_server

    return build_server()


def mcp_factory() -> Any:
    from orchestrator.mcp_client import InMemoryMcpClient

    return InMemoryMcpClient(build_mcp_server())


def factsheet_provider_for(calc: CalcPort, mcp_client: Any = None) -> Any:
    """A provider that fetches the Factsheet through the `get_factsheet` MCP tool.

    The orchestrator may not import `data/`, and `audit.run_audit` needs a
    Factsheet, which is exactly why `get_factsheet` exists
    (docs/requests/2026-09-20-p1-to-all-get-factsheet-tool.md).
    """

    def provider(context: dict) -> dict:
        client = mcp_client
        own = client is None
        if own:
            client = mcp_factory()
        try:
            response = client.call_tool(
                "get_factsheet",
                {"ticker": context["ticker"], "as_of": context["as_of"]},
            )
        finally:
            if own:
                client.close()
        factsheet = response.get("factsheet")
        if factsheet is None:
            raise ValueError(f"{context['ticker']}: get_factsheet returned no factsheet")
        if calc.last_metrics is not None:
            # So the verifier can resolve the fact_ids calc/ minted.
            factsheet = {**factsheet, "_calc_metrics": calc.last_metrics}
        return factsheet

    return provider


def real_composition(verify_claim: Any = None, redact: Any = None) -> Any:
    """Configure `orchestrator.server` with the real pieces and return the calc port."""
    from orchestrator import server

    calc = CalcPort()
    from audit.api import run_audit

    if verify_claim is None and os.environ.get("LLM_MODE", "mock").lower() == "live":
        try:
            from agents.verifier import make_verify_claim

            verify_claim = make_verify_claim()
        except Exception:  # pragma: no cover - the gate degrades to string matching
            verify_claim = None

    server.configure(
        mcp_factory,
        calc=calc,
        factsheet=factsheet_provider_for(calc),
        auditor=run_audit,
        verify_claim=verify_claim,
        redact=redact,
    )
    return calc
