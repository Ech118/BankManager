"""Append-only forward paper-trading log (plan.txt 15.14 P2 step 8; error A
fix: "Log every live prediction to predictions/ with date and input hash so
it can be graded later"). One file per run, named
<date>_<ticker>_<inputhash>.json, never overwritten and never deleted by this
module - grading a prediction later appends a NEW file, it does not mutate
the original.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from calc.value import vo_value

LOG_DIR = Path(__file__).resolve().parent / "log"


def _input_hash(ticker: str, as_of: str, verdict: dict) -> str:
    payload = json.dumps({"ticker": ticker, "as_of": as_of, "verdict": verdict}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def log_prediction(ticker: str, as_of: str, verdict: dict, log_dir: Path = LOG_DIR) -> Path:
    """Write one append-only prediction record. Returns the file path.

    Filename: <as_of>_<ticker>_<inputhash>.json (plan.txt exact naming). The
    hash is over (ticker, as_of, verdict), so re-logging an identical verdict
    for the same ticker/as_of writes the same file (idempotent), while any
    change in inputs gets its own new file - existing files are never
    modified.
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    input_hash = _input_hash(ticker, as_of, verdict)
    path = log_dir / f"{as_of}_{ticker}_{input_hash}.json"
    if path.exists():
        return path
    card = verdict.get("card", {})
    record = {
        "ticker": ticker,
        "as_of": as_of,
        "input_hash": input_hash,
        "logged_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "predicted_verdict": card.get("verdict"),
        "predicted_p_beat_sp500_5y": card.get("p_beat_sp500_5y"),
        "predicted_expected_5y_return": vo_value(card.get("expected_5y_return")),
        "predicted_scores": card.get("scores"),
        "graded": False,
        "grade": None,
        "verdict": verdict,
    }
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    return path


def list_predictions(ticker: Optional[str] = None, log_dir: Path = LOG_DIR) -> list[dict]:
    """Read back every logged prediction (optionally filtered by ticker), for
    later forward grading."""
    log_dir = Path(log_dir)
    if not log_dir.exists():
        return []
    out = []
    for path in sorted(log_dir.glob("*.json")):
        record = json.loads(path.read_text())
        if ticker is None or record.get("ticker") == ticker:
            out.append(record)
    return out


def grade_prediction(record: dict, realized_annualized_return: float,
                      sp500_realized_return: Optional[float] = None, log_dir: Path = LOG_DIR) -> Path:
    """Append a NEW file recording the grading outcome for an already-logged
    prediction; the original prediction file is left untouched (append-only)."""
    from backtest.grade import grade_case

    graded = grade_case(record["ticker"], record["as_of"], record["verdict"],
                         realized_annualized_return, sp500_realized_return)
    log_dir = Path(log_dir)
    path = log_dir / f"{record['as_of']}_{record['ticker']}_{record['input_hash']}.graded.json"
    out = dict(record)
    out["graded"] = True
    out["grade"] = graded
    out["graded_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    return path
