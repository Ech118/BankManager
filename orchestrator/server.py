"""FastAPI server: start a run, stream progress, fetch the verdict.

Specified by docs/pipeline.md.

    POST /api/analyze                 {"ticker": "ACME"} -> {"run_id"}
    GET  /api/runs/{run_id}/events    SSE {"agent","status","ts"}
    GET  /api/runs/{run_id}           the Verdict when finished

The SSE stream exists because a full run takes long enough that a spinner is not
an acceptable UI. Emitting per-agent events lets the front end show one lane per
agent, which also makes the parallel pair visible to a viewer.

Ticker input is validated against the contract's Ticker pattern before anything
else happens: it is the first line of defence for a system that feeds fetched
text to a model (error F).

TODO(roadmap Step 1, P3): the three endpoints.
TODO(roadmap Step 3, P3): SSE progress.
"""

from __future__ import annotations

from typing import Any

APP_TITLE = "BankManager research API"


def create_app() -> Any:
    """Build the FastAPI app."""
    raise NotImplementedError("TODO(roadmap Step 1, P3)")


def start_run(ticker: str, as_of: str | None = None) -> str:
    """Queue a run and return its id. Returns immediately; work happens async."""
    raise NotImplementedError("TODO(roadmap Step 1, P3)")


def get_run(run_id: str) -> dict:
    """The verdict when finished, or the current status."""
    raise NotImplementedError("TODO(roadmap Step 1, P3)")
