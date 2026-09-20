"""FastAPI server: start a run, stream progress, fetch the verdict.

Specified by docs/pipeline.md.

    POST /api/analyze                 {"ticker": "ACME"} -> {"run_id"}
    GET  /api/runs/{run_id}/events    SSE {"agent","status","ts", ...}
    GET  /api/runs/{run_id}           the Verdict when finished; 409 {"status":"preliminary"} when the
                                      run has produced evidence but no verdict yet (Steps 3-4)
    GET  /api/runs/{run_id}/report    the preliminary report: {"markdown", "state", "stats"}
    GET  /api/runs/{run_id}/stats     tokens and latency for the run
    GET  /api/config                  {"mode","llm"} so the UI can show a mock banner

The SSE stream exists because a full run takes long enough that a spinner is not
an acceptable UI. Emitting per-agent events lets the front end show one lane per
agent, which also makes the parallel pair visible to a viewer.

Ticker input is validated against the contract's Ticker pattern before anything
else happens: it is the first line of defence for a system that feeds fetched
text to a model (error F).

Run:  uvicorn orchestrator.server:app --port 8000
"""

from __future__ import annotations

import json
import os
import re
import threading
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from orchestrator import events

APP_TITLE = "BankManager research API"
TICKER_RE = re.compile(r"^[A-Z]{1,5}([.-][A-Z])?$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Composition:
    """What the process that RUNS the server injects: P3 may not import mcp_server/ or audit/."""

    def __init__(
        self,
        mcp_factory: Callable[[], Any],
        auditor=None,
        factsheet=None,
        redact=None,
        verify_claim=None,
        calc=None,
    ):
        self.mcp_factory, self.auditor, self.factsheet = mcp_factory, auditor, factsheet
        self.redact, self.verify_claim, self.calc = redact, verify_claim, calc


COMPOSITION: Composition | None = None


def configure(
    mcp_factory: Callable[[], Any],
    *,
    auditor=None,
    factsheet=None,
    redact=None,
    verify_claim=None,
    calc=None,
) -> None:
    """Wire the Coordinator to a data layer. Called once by the composition root (a script or test)."""
    global COMPOSITION
    COMPOSITION = Composition(mcp_factory, auditor, factsheet, redact, verify_claim, calc)


RUNNER: Callable[[str, str | None, str], dict] | None = None
"""(ticker, as_of, run_id) -> Verdict dict. None means orchestrator.api.run_analysis.
Tests and the future composition root set this."""


class AnalyzeRequest(BaseModel):
    ticker: str
    as_of: str | None = None


_RESULTS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


def _coordinator_runner(ticker: str, as_of: str | None, run_id: str) -> dict:
    """Run the real Coordinator so every agent's progress reaches this run's event feed.

    Returns a PRELIMINARY result (state + markdown), because until the scenario agent, red team
    and synthesizer exist (Steps 4-5) there is nothing to build a Verdict from."""
    from orchestrator.coordinator import Coordinator
    from orchestrator.report.generator import render_markdown

    comp = COMPOSITION
    assert comp is not None
    mcp = comp.mcp_factory()
    try:
        coord = Coordinator(
            mcp,
            redact=comp.redact,
            run_id=run_id,
            auditor=comp.auditor,
            factsheet=comp.factsheet,
            verify_claim=comp.verify_claim,
            calc=comp.calc,
        )
        if comp.calc is not None:  # the whole pipeline: a finished Verdict
            verdict = coord.run(ticker, as_of)
            return {"verdict": verdict.model_dump(mode="json"), "stats": coord.stats}
        state = coord.run_state(ticker, as_of)
    finally:
        mcp.close()
    return {
        "state": state.model_dump(mode="json"),
        "markdown": render_markdown(state),
        "stats": coord.stats,
    }


def _default_runner(ticker: str, as_of: str | None, run_id: str) -> dict:
    if COMPOSITION is not None:
        return _coordinator_runner(ticker, as_of, run_id)
    from orchestrator.api import run_analysis

    return run_analysis(ticker, as_of)


def start_run(ticker: str, as_of: str | None = None) -> str:
    """Queue a run and return its id. Returns immediately; work happens async."""
    run_id = events.new_run()
    with _LOCK:
        _RESULTS[run_id] = {"status": "running", "ticker": ticker, "as_of": as_of}

    def work() -> None:
        events.emit(events.AgentEvent(run_id, "run", "running"))
        try:
            verdict = (RUNNER or _default_runner)(ticker, as_of, run_id)
        except Exception as e:  # the failure is data for the client, never a server crash
            with _LOCK:
                _RESULTS[run_id].update(status="failed", error=f"{type(e).__name__}: {e}")
            events.emit(events.AgentEvent(run_id, "run", "failed", detail=str(e)))
        else:
            with _LOCK:
                if "verdict" in verdict:  # runner returned {"verdict", "stats"}
                    _RESULTS[run_id].update(
                        status="done", verdict=verdict["verdict"], stats=verdict.get("stats")
                    )
                elif "card" in verdict:
                    _RESULTS[run_id].update(status="done", verdict=verdict)
                else:
                    _RESULTS[run_id].update(status="done", preliminary=verdict)
            events.emit(events.AgentEvent(run_id, "run", "done"))
        finally:
            events.close(run_id)

    threading.Thread(target=work, name=f"run-{run_id}", daemon=True).start()
    return run_id


def get_run(run_id: str) -> dict:
    """The verdict when finished, or the current status."""
    with _LOCK:
        if run_id not in _RESULTS:
            raise KeyError(run_id)
        return dict(_RESULTS[run_id])


DEFAULT_CORS_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")


def cors_origins() -> list[str]:
    """Browser origins allowed to call the API. BM_CORS_ORIGINS="https://a.example,https://b.example"
    overrides the local Next.js dev origins. Never "*": the API starts model runs that cost money."""
    raw = os.environ.get("BM_CORS_ORIGINS", "")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    if "*" in origins:
        raise ValueError('BM_CORS_ORIGINS must list explicit origins, not "*"')
    return origins or list(DEFAULT_CORS_ORIGINS)


def create_app() -> Any:
    """Build the FastAPI app."""
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, StreamingResponse

    app = FastAPI(title=APP_TITLE)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins(),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/api/config")
    def config() -> dict:
        return {
            "mode": os.environ.get("MODE", os.environ.get("BM_MODE", "mock")),
            "llm": os.environ.get("LLM_MODE", os.environ.get("BM_LLM", "mock")),
        }

    @app.post("/api/analyze")
    def analyze(req: AnalyzeRequest) -> dict:
        ticker = req.ticker.strip().upper()
        if not TICKER_RE.match(ticker):
            raise HTTPException(
                422,
                "Ticker must be 1-5 letters, optionally with a share-class suffix (e.g. BRK.B).",
            )
        if req.as_of is not None and not DATE_RE.match(req.as_of):
            raise HTTPException(422, "as_of must be YYYY-MM-DD.")
        return {"run_id": start_run(ticker, req.as_of)}

    @app.get("/api/runs/{run_id}")
    def run(run_id: str):
        try:
            r = get_run(run_id)
        except KeyError:
            raise HTTPException(404, "Unknown run.") from None
        if r["status"] == "running":
            return JSONResponse({"status": "running"}, status_code=202)
        if r["status"] == "failed":
            return JSONResponse({"status": "failed", "error": r["error"]}, status_code=422)
        if "preliminary" in r:
            return JSONResponse(
                {
                    "status": "preliminary",
                    "detail": "No verdict yet: the scenario, red team and synthesizer steps have not run.",
                },
                status_code=409,
            )
        return r["verdict"]

    @app.get("/api/runs/{run_id}/report")
    def report(run_id: str):
        try:
            r = get_run(run_id)
        except KeyError:
            raise HTTPException(404, "Unknown run.") from None
        if "preliminary" not in r:
            raise HTTPException(404, "This run has no preliminary report.")
        return r["preliminary"]

    @app.get("/api/runs/{run_id}/stats")
    def stats(run_id: str) -> dict:
        if not events.known(run_id):
            raise HTTPException(404, "Unknown run.")
        rec = get_run(run_id)
        recorded = rec.get("stats") or rec.get("preliminary", {}).get("stats")
        if recorded:
            return recorded
        evs = events.history(run_id)
        tin = sum(e.tokens_in or 0 for e in evs)
        tout = sum(e.tokens_out or 0 for e in evs)
        return {"events": len(evs), "tokens_in": tin, "tokens_out": tout}

    @app.get("/api/runs/{run_id}/events")
    async def stream(run_id: str) -> StreamingResponse:
        if not events.known(run_id):
            raise HTTPException(404, "Unknown run.")

        async def gen():
            i = 0
            async for ev in events.subscribe(run_id):
                yield f"id: {i}\ndata: {json.dumps(ev.to_dict())}\n\n"
                i += 1

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


def __getattr__(name: str) -> Any:  # `uvicorn orchestrator.server:app` builds the app lazily
    if name == "app":
        app = create_app()
        globals()["app"] = app
        return app
    raise AttributeError(name)
