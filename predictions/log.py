"""Append-only prediction log writer.

Specified by docs/roadmap.md Step 6.

One file per run: predictions/<date>_<ticker>_<inputhash>.json

The input hash covers the factsheet, the metrics and the prompt versions, so a
later reader can tell whether two predictions were made from the same evidence
by the same pipeline. Without it, a changed prompt silently invalidates every
comparison.

Records the stated probability AT THE TIME. Grading later compares against the
realized excess return; nothing in this module may be rewritten afterwards.

TODO(roadmap Step 6, P2).
"""

from __future__ import annotations

from pathlib import Path

from schema.contracts.verdict import Verdict

LOG_DIR = Path(__file__).resolve().parent / "log"
"""Gitignored data directory. The code lives here; the records do not ship."""


def input_hash(factsheet: dict, metrics: dict, prompt_versions: dict[str, str]) -> str:
    """Stable hash of everything that could change a prediction."""
    raise NotImplementedError("TODO(roadmap Step 6, P2)")


def record(verdict: Verdict, factsheet: dict, metrics: dict, prompt_versions: dict) -> Path:
    """Append one prediction. Raises if the file already exists.

    Refusing to overwrite is the point: an append-only log that silently
    replaces entries is just a log.
    """
    raise NotImplementedError("TODO(roadmap Step 6, P2)")


def due_for_grading(as_of: str, horizon: str) -> list[Path]:
    """Predictions whose horizon has now elapsed."""
    raise NotImplementedError("TODO(roadmap Step 6, P2)")
