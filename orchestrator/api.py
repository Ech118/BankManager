"""P3 (Agents, Orchestrator & Web) owns this file. Public interface of the pipeline.

Step 0 STUB: returns the ACME verdict fixture. The owner replaces the internals
but MUST NOT change the signature (plan.txt 15.11).

HTTP interface (implemented by P3 in orchestrator/server.py):
    POST /api/analyze                 body {"ticker": "ACME"} -> {"run_id": str}
    GET  /api/runs/{run_id}/events    Server-Sent Events {"agent","status","ts"}
    GET  /api/runs/{run_id}           verdict.json when finished
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

_MOCK = Path(__file__).resolve().parents[1] / "fixtures" / "mock"


def run_analysis(ticker: str, as_of: str | None = None,
                 redact: Callable[[str], str] | None = None) -> dict:
    """Run the whole pipeline and return verdict.json.

    redact(text) -> text is applied to ALL filing text before any agent sees it.
    The backtest passes an anonymizer (error A); live mode passes None.
    Raises ValueError if data.api.check_scope says the ticker is out of scope.
    """
    if os.environ.get("BM_MODE", "mock").lower() == "live":
        raise NotImplementedError("orchestrator.api.run_analysis: live mode is not implemented yet (P3). Use BM_MODE=mock.")
    if ticker != "ACME":
        raise ValueError("Mock mode only knows the fictional ticker ACME.")
    return json.loads((_MOCK / "verdict.json").read_text())
