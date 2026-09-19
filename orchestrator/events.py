"""Per-agent progress events for the UI lanes, and the run log.

Specified by docs/pipeline.md.

One event per agent state change. The UI renders a lane per agent, so a viewer
can see the financial and business agents running at the same time rather than
watching a single progress bar.

Also the place token counts per agent land, which is how per-run cost gets
measured rather than estimated (error K).
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from schema.contracts.enums import AgentName

STATUSES = ("pending", "running", "retrying", "done", "failed")
"""`retrying` is shown explicitly: a reader of the live view should be able to
see that a section was sent back, not just that it took longer."""

RUN_LOG = Path(__file__).resolve().parent / "logs" / "runs.jsonl"
MAX_RUNS = 200


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class AgentEvent:
    """One state change, as sent over SSE.

    `agent` is an AgentName for the roster and a plain stage name ("ingest",
    "verify", "report", "run") for pipeline stages that are not agents.
    """

    run_id: str
    agent: AgentName | str
    status: str
    ts: str = field(default_factory=now_iso)
    detail: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["agent"] = str(getattr(self.agent, "value", self.agent))
        return {k: v for k, v in d.items() if v is not None}


class _Feed:
    def __init__(self) -> None:
        self.events: list[AgentEvent] = []
        self.closed = False
        self.created = time.time()
        self.lock = threading.Lock()


_FEEDS: dict[str, _Feed] = {}
_FEEDS_LOCK = threading.Lock()


def new_run() -> str:
    """Register a run and return its id."""
    run_id = uuid.uuid4().hex[:12]
    with _FEEDS_LOCK:
        if len(_FEEDS) >= MAX_RUNS:  # forget the oldest finished run
            for rid, feed in sorted(_FEEDS.items(), key=lambda kv: kv[1].created):
                if feed.closed:
                    del _FEEDS[rid]
                    break
        _FEEDS[run_id] = _Feed()
    return run_id


def emit(event: AgentEvent) -> None:
    """Publish to the run's subscribers. Unknown runs are ignored (a test may not register)."""
    feed = _FEEDS.get(event.run_id)
    if feed is not None:
        with feed.lock:
            feed.events.append(event)


def close(run_id: str) -> None:
    feed = _FEEDS.get(run_id)
    if feed is not None:
        feed.closed = True


def history(run_id: str) -> list[AgentEvent]:
    feed = _FEEDS.get(run_id)
    if feed is None:
        return []
    with feed.lock:
        return list(feed.events)


def known(run_id: str) -> bool:
    return run_id in _FEEDS


async def subscribe(run_id: str) -> AsyncIterator[AgentEvent]:
    """Async iterator of events for one run. Replays history, then follows live."""
    feed = _FEEDS.get(run_id)
    if feed is None:
        raise KeyError(run_id)
    sent = 0
    while True:
        with feed.lock:
            batch, closed = feed.events[sent:], feed.closed
        for ev in batch:
            yield ev
            sent += 1
        if closed and not batch:
            return
        await asyncio.sleep(0.05)


def log_run(stats: dict) -> None:
    """Append one JSON line per run (tokens, latency, cost). Never fails a run."""
    try:
        RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
        with RUN_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(stats) + "\n")
    except OSError:
        pass
