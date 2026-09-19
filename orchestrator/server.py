"""FastAPI server (plan.txt 15.8).

    POST /api/analyze              {"ticker": "ACME", "as_of": null} -> {"run_id"}
    GET  /api/runs/{id}/events     Server-Sent Events {"agent","status","ts", ...}
    GET  /api/runs/{id}            200 verdict.json | 202 running | 422 failed | 404 unknown
    GET  /api/runs/{id}/stats      tokens, latency, estimated cost per agent
    GET  /api/config               {"mode","llm"} so the UI can show a mock banner

Run:  uvicorn orchestrator.server:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import threading

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from . import runlog
from .events import RunRecord, RunStore
from .pipeline import Pipeline

TICKER_RE = re.compile(r"^[A-Z]{1,5}([.-][A-Z])?$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

app = FastAPI(title="BankManager API")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
                   allow_methods=["GET", "POST"], allow_headers=["*"])
store = RunStore()


class AnalyzeRequest(BaseModel):
    ticker: str
    as_of: str | None = None


def _execute(rec: RunRecord) -> None:
    pipe = Pipeline(emit=rec.emit)
    try:
        verdict = pipe.run(rec.ticker, rec.as_of)
    except Exception as e:  # the run's failure is data for the client, never a server crash
        rec.fail(f"{type(e).__name__}: {e}", pipe.stats)
        runlog.append({**pipe.stats, "error": str(e)})
        return
    rec.finish(verdict, pipe.stats)
    runlog.append(pipe.stats)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/config")
def config() -> dict:
    return {"mode": os.environ.get("BM_MODE", "mock"), "llm": os.environ.get("BM_LLM", "mock")}


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest) -> dict:
    ticker = req.ticker.strip().upper()
    if not TICKER_RE.match(ticker):          # validated before it reaches any tool or prompt (error F)
        raise HTTPException(422, "Ticker must be 1-5 letters, optionally with a share-class suffix (e.g. BRK.B).")
    if req.as_of is not None and not DATE_RE.match(req.as_of):
        raise HTTPException(422, "as_of must be YYYY-MM-DD.")
    rec = store.create(ticker, req.as_of)
    threading.Thread(target=_execute, args=(rec,), daemon=True).start()
    return {"run_id": rec.run_id}


def _get(run_id: str) -> RunRecord:
    rec = store.get(run_id)
    if rec is None:
        raise HTTPException(404, "Unknown run.")
    return rec


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    rec = _get(run_id)
    if rec.status == "running":
        return JSONResponse({"status": "running"}, status_code=202)
    if rec.status == "failed":
        return JSONResponse({"status": "failed", "error": rec.error}, status_code=422)
    return rec.verdict


@app.get("/api/runs/{run_id}/stats")
def get_stats(run_id: str) -> dict:
    return _get(run_id).stats or {}


@app.get("/api/runs/{run_id}/events")
async def events(run_id: str) -> StreamingResponse:
    rec = _get(run_id)

    async def stream():
        sent = 0
        while True:
            new, finished = rec.snapshot(sent)
            for ev in new:
                yield f"id: {sent}\ndata: {json.dumps(ev)}\n\n"
                sent += 1
            if finished and not new:
                return
            if not new:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.1)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
