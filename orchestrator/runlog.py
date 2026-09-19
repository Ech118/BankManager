"""Append one JSON line per run (tokens, latency, estimated cost) to orchestrator/logs/runs.jsonl."""
from __future__ import annotations

import json
from pathlib import Path

LOG = Path(__file__).resolve().parent / "logs" / "runs.jsonl"


def append(stats: dict) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as f:
            f.write(json.dumps(stats) + "\n")
    except OSError:
        pass  # logging must never fail a run
