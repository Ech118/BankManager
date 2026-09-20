"""Run the pipeline for a list of tickers and save each Verdict for the web demo.

    MODE=live LLM_MODE=live python -m backtest.demo_run AAPL NVDA MSFT KO JPM

Writes `web/public/demo/<TICKER>.json` per ticker, plus `index.json` listing the
ones that finished. A failure is recorded and skipped: one bad ticker must not
cost the other four.
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "public" / "demo"


def run_one(ticker: str) -> dict:
    from orchestrator.api import run_analysis

    started = time.time()
    try:
        verdict = run_analysis(ticker)
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"{ticker}.json").write_text(
            json.dumps(verdict, indent=2), encoding="utf-8"
        )
        card = verdict.get("card", {})
        return {
            "ticker": ticker,
            "ok": True,
            "seconds": round(time.time() - started, 1),
            "verdict": card.get("verdict"),
            "scores": card.get("scores"),
            "company": card.get("company"),
        }
    except Exception as exc:  # noqa: BLE001 - every failure is reported, none is fatal
        return {
            "ticker": ticker,
            "ok": False,
            "seconds": round(time.time() - started, 1),
            "error": f"{type(exc).__name__}: {exc}"[:400],
            "where": traceback.format_exc(limit=3)[-600:],
        }


def main(tickers: list[str]) -> int:
    results = [run_one(ticker) for ticker in tickers]
    for row in results:
        if row["ok"]:
            print(f"{row['ticker']:6} OK   {row['seconds']:6.1f}s  {row['verdict']} {row['scores']}")
        else:
            print(f"{row['ticker']:6} FAIL {row['seconds']:6.1f}s  {row['error']}")
    done = [row for row in results if row["ok"]]
    if done:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "index.json").write_text(
            json.dumps(
                {
                    "tickers": [row["ticker"] for row in done],
                    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "runs": results,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    return 0 if done else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or ["ACME"]))
