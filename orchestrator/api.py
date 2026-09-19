"""P3 (Agents, Orchestrator & Web) owns this file. Public interface of the pipeline.

Step 0 STUB: returns the ACME verdict fixture. The owner replaces the internals
but MUST NOT change the signature (CONTRACT-CHANGE PR, CONTRIBUTING.md).

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

import json
import os
from collections.abc import Callable
from pathlib import Path

_MOCK = Path(__file__).resolve().parents[1] / "fixtures" / "mock"


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
    if os.environ.get("MODE", os.environ.get("BM_MODE", "mock")).lower() == "live":
        raise NotImplementedError(
            "orchestrator.api.run_analysis: live mode is not implemented yet "
            "(P3, roadmap Step 1). Use MODE=mock."
        )
    if ticker != "ACME":
        raise ValueError("Mock mode only knows the fictional ticker ACME.")
    return json.loads((_MOCK / "verdict.json").read_text(encoding="utf-8"))
