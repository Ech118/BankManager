"""FastAPI server: start a run, stream progress, fetch the verdict.

Specified by docs/pipeline.md.

    POST /api/analyze                 {"ticker": "ACME"} -> {"run_id"}
    GET  /api/runs/{run_id}/events    SSE {"agent","status","ts", ...}
    GET  /api/runs/{run_id}           the Verdict when finished
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

RUNNER: Callable[[str, str | None, str], dict] | None = None
"""(ticker, as_of, run_id) -> Verdict dict. None means orchestrator.api.run_analysis.
Tests and the future composition root set this."""


class AnalyzeRequest(BaseModel):
    ticker: str
    as_of: str | None = None


_RESULTS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


def _default_runner(ticker: str, as_of: str | None, run_id: str) -> dict:
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
                _RESULTS[run_id].update(status="done", verdict=verdict)
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


def create_app() -> Any:
    """Build the FastAPI app."""
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, StreamingResponse

    app = FastAPI(title=APP_TITLE)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
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
        return r["verdict"]

    @app.get("/api/runs/{run_id}/stats")
    def stats(run_id: str) -> dict:
        if not events.known(run_id):
            raise HTTPException(404, "Unknown run.")
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
