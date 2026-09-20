"""P3 (Agents, Orchestrator & Web) owns this file. Public interface of the pipeline.

Runs the real pipeline. The three things P3 may not import - mcp_server/, calc/
and audit/ - are wired in by `orchestrator/composition.py`, the one file in the
process that imports them, and reach the Coordinator as injected ports.

BOUNDARY (docs/adr/0007): P3 reaches data ONLY through MCP tools, never by
importing data/ or calc/. orchestrator/mcp_client.py speaks the MCP SDK's
in-memory transport in mock mode and tests, and stdio in live mode, so the
boundary is exercised either way (docs/mcp-tools.md).

HTTP interface (orchestrator/server.py):
    POST /api/analyze                 body {"ticker": "ACME"} -> {"run_id": str}
    GET  /api/runs/{run_id}/events    Server-Sent Events {"agent","status","ts"}
    GET  /api/runs/{run_id}           the Verdict when finished
"""

from __future__ import annotations

import os
from collections.abc import Callable


def run_analysis(
    ticker: str, as_of: str | None = None, redact: Callable[[str], str] | None = None
) -> dict:
    """Run the whole pipeline and return a Verdict (schema/verdict.json).

    Pipeline (docs/pipeline.md):
        ingest -> financial || business -> valuation -> scenario -> red_team
        -> calc.evaluate_scenarios -> synthesizer -> audit
        -> targeted retry (max 2) -> report generator

    `redact(text) -> text` is applied to ALL filing text before any agent sees
    it. The backtest passes an anonymizer so the model cannot recognise the
    company and recall what happened next (error A, ADR 0003); live mode passes
    None.

    Raises ValueError if data.api.check_scope says the ticker is out of scope.
    """
    from orchestrator.composition import CalcPort, factsheet_provider_for, mcp_factory
    from orchestrator.coordinator import Coordinator

    calc = CalcPort()
    verify_claim = None
    if os.environ.get("LLM_MODE", "mock").lower() == "live":
        try:
            from agents.verifier import make_verify_claim

            verify_claim = make_verify_claim()
        except Exception:  # the gate degrades to string matching rather than failing
            verify_claim = None

    from audit.api import run_audit

    mcp = mcp_factory()
    try:
        coordinator = Coordinator(
            mcp,
            redact=redact,
            calc=calc,
            auditor=run_audit,
            factsheet=factsheet_provider_for(calc, mcp),
            verify_claim=verify_claim,
        )
        verdict = coordinator.run(ticker, as_of)
    finally:
        mcp.close()
    return verdict.model_dump(mode="json")
