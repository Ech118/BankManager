"""In-memory run registry and progress events (thread-safe). One lane per agent in the UI."""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class RunRecord:
    run_id: str
    ticker: str
    as_of: str | None
    status: str = "running"            # running | done | failed
    events: list[dict] = field(default_factory=list)
    verdict: dict | None = None
    error: str | None = None
    stats: dict | None = None
    created: float = field(default_factory=time.time)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def emit(self, agent: str, status: str, **extra) -> None:
        ev = {"agent": agent, "status": status, "ts": now_iso(), **extra}
        with self._lock:
            self.events.append(ev)

    def snapshot(self, start: int) -> tuple[list[dict], bool]:
        with self._lock:
            return self.events[start:], self.status != "running"

    def finish(self, verdict: dict, stats: dict) -> None:
        with self._lock:
            self.verdict, self.stats, self.status = verdict, stats, "done"
        self.emit("run", "done")

    def fail(self, error: str, stats: dict | None = None) -> None:
        with self._lock:
            self.error, self.stats, self.status = error, stats, "failed"
        self.emit("run", "failed", detail=error)


class RunStore:
    MAX_RUNS = 200

    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._lock = threading.Lock()

    def create(self, ticker: str, as_of: str | None) -> RunRecord:
        rec = RunRecord(uuid.uuid4().hex[:12], ticker, as_of)
        with self._lock:
            if len(self._runs) >= self.MAX_RUNS:  # drop the oldest finished run
                done = sorted((r for r in self._runs.values() if r.status != "running"), key=lambda r: r.created)
                for r in done[: len(self._runs) - self.MAX_RUNS + 1]:
                    self._runs.pop(r.run_id, None)
            self._runs[rec.run_id] = rec
        return rec

    def get(self, run_id: str) -> RunRecord | None:
        with self._lock:
            return self._runs.get(run_id)
