"""Per-agent progress events for the UI lanes.

Specified by docs/pipeline.md.

One event per agent state change. The UI renders a lane per agent, so a viewer
can see the financial and business agents running at the same time rather than
watching a single progress bar.

Also the run log: token counts per agent land here, which is how per-run cost
gets measured rather than estimated (error K).

TODO(roadmap Step 3, P3).
"""

from __future__ import annotations

from dataclasses import dataclass

from schema.contracts.enums import AgentName

STATUSES = ("pending", "running", "retrying", "done", "failed")
"""`retrying` is shown explicitly: a reader of the live view should be able to
see that a section was sent back, not just that it took longer."""


@dataclass(frozen=True)
class AgentEvent:
    """One state change, as sent over SSE."""

    run_id: str
    agent: AgentName
    status: str
    ts: str
    detail: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None


def emit(event: AgentEvent) -> None:
    """Publish to the run's subscribers."""
    raise NotImplementedError("TODO(roadmap Step 3, P3)")


def subscribe(run_id: str):
    """Async iterator of events for one run."""
    raise NotImplementedError("TODO(roadmap Step 3, P3)")
