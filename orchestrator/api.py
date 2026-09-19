"""P3 (Agents, Orchestrator & Web) owns this file. Public interface of the pipeline.

The signature is FROZEN (plan.txt 15.11). Internals live in orchestrator/pipeline.py.

HTTP interface (implemented in orchestrator/server.py):
    POST /api/analyze                 body {"ticker": "ACME"} -> {"run_id": str}
    GET  /api/runs/{run_id}/events    Server-Sent Events {"agent","status","ts"}
    GET  /api/runs/{run_id}           verdict.json when finished
"""
from __future__ import annotations

from typing import Callable

from . import runlog
from .pipeline import Pipeline


def run_analysis(ticker: str, as_of: str | None = None,
                 redact: Callable[[str], str] | None = None) -> dict:
    """Run the whole pipeline and return verdict.json.

    redact(text) -> text is applied to ALL filing text before any agent sees it.
    The backtest passes an anonymizer (error A); live mode passes None.
    Raises ValueError if data.api.check_scope says the ticker is out of scope.
    """
    pipe = Pipeline()
    verdict = pipe.run(ticker, as_of, redact)
    runlog.append(pipe.stats)
    return verdict
