"""Shared setup for P2's unit tests.

The real recordings in `fixtures/real/<TICKER>/factsheet.json` are as much a part
of the test suite as the ACME mock: the mock cannot expose a formula that breaks
on a bank, a stock split or an untagged interest expense, and all three are
sitting in the recordings.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from calc.tests.support import REAL_TICKERS, load_mock, load_real  # noqa: E402


@pytest.fixture
def acme() -> dict:
    return load_mock("factsheet.json")


@pytest.fixture
def pinned_metrics() -> dict:
    """fixtures/mock/metrics.json: the hand-checked ACME numbers."""
    return load_mock("metrics.json")


@pytest.fixture(params=REAL_TICKERS)
def real_factsheet(request) -> dict:
    return load_real(request.param)
