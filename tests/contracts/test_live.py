"""Rule 3: live-mode check. Skipped unless run as: BM_MODE=live BM_TEST_TICKER=<ticker> make check-live
FROZEN (Step 0)."""
import os

import pytest
from conftest import ORIGINAL_BM_MODE
from helpers import validation_errors

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(ORIGINAL_BM_MODE != "live" or not os.environ.get("BM_TEST_TICKER"),
                       reason="set BM_MODE=live and BM_TEST_TICKER=<ticker> to run"),
]


def test_live_factsheet_validates():
    from data import api
    ticker = os.environ["BM_TEST_TICKER"]
    assert api.check_scope(ticker)["in_scope"]
    errs = validation_errors(api.build_factsheet(ticker), "factsheet.json")
    assert not errs, "\n".join(errs)
