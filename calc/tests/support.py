"""Fixture loaders shared by P2's tests.

A module rather than conftest globals, because `calc/tests` is a package (so that
pytest can collect it beside the other partitions' `test_placeholders.py`) and a
bare `from conftest import ...` no longer resolves.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOCK = ROOT / "fixtures" / "mock"
REAL = ROOT / "fixtures" / "real"

REAL_TICKERS = ["AAPL", "NVDA", "MSFT", "KO", "JPM"]
"""The five the roadmap names: a no-interest filer, a split, a normal large cap,
a clean consumer staple, and a bank."""


def load_mock(name: str) -> dict:
    return json.loads((MOCK / name).read_text(encoding="utf-8"))


def load_real(ticker: str) -> dict:
    return json.loads((REAL / ticker / "factsheet.json").read_text(encoding="utf-8"))
